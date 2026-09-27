#!/usr/bin/env python3
"""GATE 4 — HBM 바이트를 줄이면 스텝 시간이 그만큼 주는가.

논문의 모든 성능 수치가 ΔT = ΔD / B_eff 위에 있다. B_eff (B200 에서 6.40 TB/s) 는
서로 다른 (배치, 문맥) 앵커 사이의 회귀 기울기이지, **같은 워크로드에서 HBM 바이트만
줄였을 때의 인과적 한계율이 아니다.** 이 스크립트가 그것을 잰다.

통제 변수는 하나: persisting L2 예약 크기. 워크로드는 완전히 고정한다.
스윕 점은 gpu00_probe.py 가 기계에서 읽은 persistingL2CacheMaxSize 에서 유도한다 —
어떤 문서의 숫자도 하드코딩하지 않으므로 B200/H200/B300/RTX 어디서나 그대로 돈다.

두 패스로 나눈다. 프로파일러를 켠 채 시간을 재면 그 시간이 오염되기 때문이다.
  pass T : 프로파일러 없음. 깨끗한 step 시간.            -> ΔT 축
  pass D : ncu 로 dram__bytes_*, lts__t_sector_hit_rate.pct  -> ΔD 축 + L2 적중 실측
같은 조건·같은 시드로 두 번 돌리고 조건 키로 합친다.

  python3 gpu01_causal_sweep.py --mode vllm  --steps 1000 --reps 3
  python3 gpu01_causal_sweep.py --mode synth --steps 1000 --reps 3   # vLLM 없이 가능
"""
import argparse, ctypes, json, os, socket, statistics, subprocess, sys, time
from pathlib import Path

CUDART = None
for lib in ('libcudart.so', 'libcudart.so.12', 'libcudart.so.13', 'libcudart.so.11.0'):
    try: CUDART = ctypes.CDLL(lib); break
    except OSError: continue
LIMIT_PERSISTING_L2 = 0x06   # cudaLimitPersistingL2CacheSize (0x05 는 MaxL2FetchGranularity — 2026-09-24 정정)
ATTR_MAX_PERSISTING_L2 = 108

def persist_max():
    v = ctypes.c_int(0)
    if CUDART and CUDART.cudaDeviceGetAttribute(ctypes.byref(v), ATTR_MAX_PERSISTING_L2, 0) == 0:
        return v.value
    return 0

def set_persist(nbytes):
    """L2 에서 persisting 용으로 떼어낼 바이트. 0 이면 기능 끔."""
    if not CUDART: return False
    rc = CUDART.cudaDeviceSetLimit(ctypes.c_int(LIMIT_PERSISTING_L2), ctypes.c_size_t(int(nbytes)))
    got = ctypes.c_size_t(0)
    CUDART.cudaDeviceGetLimit(ctypes.byref(got), ctypes.c_int(LIMIT_PERSISTING_L2))
    return rc == 0 and abs(got.value - int(nbytes)) <= max(1 << 20, int(nbytes) * 0.05)

# ---------------------------------------------------------------- 워크로드 A: 실제 vLLM
def run_vllm(steps, persist_bytes, seed=20260923):
    """Llama-3.1-8B, 배치 8, 문맥 2048, BF16, prefix cache 끔 — 기존 앵커와 동일 조건."""
    from vllm import LLM, SamplingParams
    import torch
    set_persist(persist_bytes)
    llm = LLM(model=os.environ.get('MODEL', 'meta-llama/Llama-3.1-8B'),
              dtype='bfloat16', enable_prefix_caching=False, max_num_seqs=8,
              gpu_memory_utilization=0.85, seed=seed, enforce_eager=False)
    prompts = ['The quick brown fox jumps over the lazy dog. ' * 128] * 8   # ~2048 tok
    sp = SamplingParams(max_tokens=steps, min_tokens=steps, temperature=0.0, ignore_eos=True)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    out = llm.generate(prompts, sp)
    torch.cuda.synchronize(); t1 = time.perf_counter()
    ntok = sum(len(o.outputs[0].token_ids) for o in out)
    del llm; torch.cuda.empty_cache()
    return dict(wall_s=t1-t0, tokens=ntok, step_ms=(t1-t0)*1000/max(1, steps))

# ---------------------------------------------------------------- 워크로드 B: 합성 decode
def run_synth(steps, persist_bytes, seed=20260923):
    """decode 의 트래픽 구조만 재현한다: 스텝마다 W 바이트 weight 를 한 번씩 훑고
    배치만큼의 GEMV 를 한다. 재사용 거리 = working set 이라는 성질이 같으므로
    같은 인과 질문에 답한다. vLLM 이 없거나 vLLM 쪽 변수를 배제하고 싶을 때 쓴다."""
    import torch
    torch.manual_seed(seed)
    set_persist(persist_bytes)
    free, total = torch.cuda.mem_get_info()
    W_GB = float(os.environ.get('SYNTH_W_GB', '12'))
    n = int(W_GB * 1e9 / 2 / 4096)                       # bf16, 4096 열
    Wt = torch.randn(n, 4096, device='cuda', dtype=torch.bfloat16)
    x  = torch.randn(8, 4096, device='cuda', dtype=torch.bfloat16)
    for _ in range(5): (x @ Wt.T[:, :4096].contiguous().T)      # 워밍업
    torch.cuda.synchronize()
    ts = []
    for _ in range(steps):
        t0 = time.perf_counter()
        y = x @ Wt.T
        torch.cuda.synchronize()
        ts.append((time.perf_counter() - t0) * 1000)
    del Wt, x; torch.cuda.empty_cache()
    return dict(step_ms=statistics.median(ts), step_ms_p99=sorted(ts)[int(.99*len(ts))-1],
                logical_read_GB=W_GB, samples=len(ts))

# ---------------------------------------------------------------- pass D: 카운터
NCU_METRICS = 'dram__bytes_read.sum,dram__bytes_write.sum,lts__t_sector_hit_rate.pct'
def run_counters(mode, steps, persist_bytes, out_csv):
    """같은 조건을 ncu 아래에서 다시 돌려 바이트를 딴다. 시간은 여기서 쓰지 않는다."""
    ncu = os.environ.get('NCU', 'ncu')
    cmd = (f'{ncu} --metrics {NCU_METRICS} --csv --target-processes all '
           f'--kernel-name-base function -f -o /dev/null '
           f'{sys.executable} {__file__} --mode {mode} --steps {max(20, steps//20)} '
           f'--persist-bytes {persist_bytes} --inner')
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    Path(out_csv).write_text(p.stdout + '\n#STDERR\n' + p.stderr)
    return p.returncode

# ---------------------------------------------------------------- 본체
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=('vllm', 'synth'), default='vllm')
    ap.add_argument('--steps', type=int, default=1000)
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--persist-bytes', type=int, default=None)
    ap.add_argument('--inner', action='store_true', help='ncu 가 부르는 1회 실행')
    ap.add_argument('--skip-counters', action='store_true')
    a = ap.parse_args()
    fn = run_vllm if a.mode == 'vllm' else run_synth

    if a.inner:
        fn(a.steps, a.persist_bytes or 0); return

    PM = persist_max()
    if not PM:
        print('persistingL2CacheMaxSize 를 못 읽었다. gpu00_probe.py 를 먼저 돌려라.'); sys.exit(1)
    pts = [0] + [int(PM * f) for f in (0.2, 0.4, 0.6, 0.8, 1.0)]
    host = socket.gethostname()
    outdir = Path(f'gate4_{host}_{a.mode}'); outdir.mkdir(exist_ok=True)
    print(f'기계 {host}  persisting 상한 {PM:,} B ({PM/2**20:.1f} MiB)')
    print(f'스윕 {[round(p/2**20,1) for p in pts]} MiB   steps={a.steps} reps={a.reps}\n')

    rows = []
    for pb in pts:
        for rep in range(a.reps):
            ok = set_persist(pb)
            r = fn(a.steps, pb)
            r.update(persist_bytes=pb, persist_MiB=round(pb/2**20, 2), rep=rep,
                     set_ok=ok, mode=a.mode, host=host, steps=a.steps)
            rows.append(r)
            print(f'  persist {pb/2**20:7.1f} MiB  rep{rep}  step {r["step_ms"]:.4f} ms')
        if not a.skip_counters:
            rc = run_counters(a.mode, a.steps, pb, outdir/f'ncu_{pb}.csv')
            print(f'  persist {pb/2**20:7.1f} MiB  카운터 rc={rc} -> ncu_{pb}.csv')
    (outdir/'timing.json').write_text(json.dumps(rows, indent=2))
    print(f'\n저장: {outdir}/  (timing.json + ncu_*.csv). 로컬로 가져와 gpu02_analyze.py')

if __name__ == '__main__':
    main()
