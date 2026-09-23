#!/usr/bin/env python3
"""GATE 0 — 돈 쓰기 전에 5분 안에 돌려야 하는 유일한 스크립트.

이것이 통과하지 못하면 어떤 GPU 를 빌려도 Gate 4 를 할 수 없다. 이전 B200 실험이
정확히 여기서 실패했다("카운터 접근 불가", memory.html).

확인 네 가지
  1. 기계 신원과 L2 / persisting 상한  -> 스윕 범위를 여기서 유도한다(하드코딩 금지)
  2. GPU 성능 카운터 접근 권한 (ncu)   -> ERR_NVGPUCTRPERM 이면 즉시 중단
  3. Nsight Systems 존재               -> 커널 타임라인용
  4. persisting L2 API 가 실제로 먹는가 -> 드라이버 API 왕복 확인

의존성: torch(또는 pynvml), CUDA 툴킷의 ncu/nsys. vLLM 불필요.
사용:   python3 gpu00_probe.py            결과는 gpu_probe_<host>.json
"""
import json, os, shutil, socket, subprocess, sys, tempfile, textwrap, time
from pathlib import Path

OUT = {}
def say(k, v, ok=None):
    mark = '' if ok is None else ('  [OK]' if ok else '  [FAIL]')
    print(f'{k:38} {v}{mark}'); OUT[k] = v

def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, '', str(e)

print('=' * 74); print('GATE 0 — 환경 프로브'); print('=' * 74)
say('host', socket.gethostname())

# ---------------------------------------------------------------- 1. 기계 신원
try:
    import torch
    d = torch.cuda.get_device_properties(0)
    say('gpu.name', d.name)
    say('gpu.capability', f'{d.major}.{d.minor}')
    say('gpu.total_mem_GB', round(d.total_memory/1e9, 1))
    say('gpu.l2_cache_bytes', getattr(d, 'L2_cache_size', None))
    say('gpu.multi_processor_count', d.multi_processor_count)
    say('torch.version', torch.__version__)
    say('torch.cuda', torch.version.cuda)
except Exception as e:
    say('gpu.props', f'torch 실패: {e}', ok=False)

# persistingL2CacheMaxSize 는 torch props 에 없으므로 드라이버에서 직접
PERSIST_MAX = None
try:
    import ctypes
    cudart = None
    for lib in ('libcudart.so', 'libcudart.so.12', 'libcudart.so.13', 'libcudart.so.11.0'):
        try: cudart = ctypes.CDLL(lib); break
        except OSError: continue
    if cudart is None: raise OSError('libcudart 못 찾음')
    # cudaDeviceGetAttribute(&v, cudaDevAttrMaxPersistingL2CacheSize=108, device=0)
    v = ctypes.c_int(0)
    rc = cudart.cudaDeviceGetAttribute(ctypes.byref(v), 108, 0)
    if rc == 0 and v.value > 0:
        PERSIST_MAX = v.value
        say('gpu.persisting_l2_max_bytes', PERSIST_MAX, ok=True)
    else:
        say('gpu.persisting_l2_max_bytes', f'rc={rc} v={v.value}', ok=False)
    # 실제로 설정이 먹는지 왕복 확인: cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize=0x05, n)
    if PERSIST_MAX:
        half = PERSIST_MAX // 2
        rc2 = cudart.cudaDeviceSetLimit(ctypes.c_int(0x05), ctypes.c_size_t(half))
        got = ctypes.c_size_t(0)
        rc3 = cudart.cudaDeviceGetLimit(ctypes.byref(got), ctypes.c_int(0x05))
        ok = (rc2 == 0 and rc3 == 0 and got.value > 0)
        say('persisting_l2.set_get_roundtrip', f'set rc={rc2}, get rc={rc3}, got={got.value}', ok=ok)
        cudart.cudaDeviceSetLimit(ctypes.c_int(0x05), ctypes.c_size_t(0))
except Exception as e:
    say('persisting_l2.api', f'실패: {e}', ok=False)

# ---------------------------------------------------------------- 2. 카운터 권한 ★
NCU = shutil.which('ncu') or shutil.which('nv-nsight-cu-cli')
say('tool.ncu', NCU or '없음', ok=bool(NCU))
counters_ok = False
if NCU:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td)/'t.cu'
        src.write_text(textwrap.dedent('''
            __global__ void k(float*a,int n){int i=blockIdx.x*blockDim.x+threadIdx.x;
              if(i<n) a[i]=a[i]*1.000001f+1.0f;}
            int main(){float*a;cudaMalloc(&a,1<<22);
              for(int i=0;i<3;i++) k<<<4096,256>>>(a,1<<20);
              cudaDeviceSynchronize();cudaFree(a);return 0;}'''))
        rc, so, se = run(f'nvcc -o {td}/t {src} 2>&1')
        if rc != 0:
            say('counters.compile', 'nvcc 실패 — CUDA 툴킷 확인', ok=False)
        else:
            rc, so, se = run(f'{NCU} --metrics dram__bytes_read.sum,lts__t_sectors_hit_rate '
                             f'--csv --target-processes all {td}/t')
            blob = so + se
            if 'ERR_NVGPUCTRPERM' in blob or 'insufficient permissions' in blob.lower():
                say('counters.permission', 'ERR_NVGPUCTRPERM — 권한 없음', ok=False)
                print('\n  >> 업체에 요청할 문장:')
                print('     "NVreg_RestrictProfilingToAdminUsers=0 으로 설정해 주시거나,')
                print('      인스턴스에서 sudo/CAP_SYS_ADMIN 으로 ncu 를 실행하게 해 주세요."')
                print('  >> sudo 가 있다면: sudo $(which ncu) ... 로 재시도')
            elif 'dram__bytes_read' in blob:
                counters_ok = True
                say('counters.permission', 'dram__bytes_read 수집 성공', ok=True)
            else:
                say('counters.permission', f'불명 (rc={rc}) — 아래 원문 확인', ok=False)
                print('  ' + blob[-900:].replace('\n', '\n  '))
OUT['counters_ok'] = counters_ok

NSYS = shutil.which('nsys')
say('tool.nsys', NSYS or '없음', ok=bool(NSYS))

# ---------------------------------------------------------------- 3. 스윕 범위 유도
if PERSIST_MAX:
    pts = [0] + [int(PERSIST_MAX * f) for f in (0.2, 0.4, 0.6, 0.8, 1.0)]
    say('sweep.persist_bytes', pts)
    say('sweep.persist_MiB', [round(p/2**20, 1) for p in pts])
    print('\n  이 값은 기계에서 읽은 것이다. 어떤 문서의 숫자도 하드코딩하지 않는다.')

# ---------------------------------------------------------------- 판정
print('\n' + '=' * 74)
go = counters_ok and bool(PERSIST_MAX)
print('판정:', 'GO — Gate 4 진행 가능' if go else 'NO-GO — 아래를 먼저 해결')
if not counters_ok: print('  · GPU 성능 카운터 권한 (치명적)')
if not PERSIST_MAX: print('  · persisting L2 API 접근')
if not NSYS: print('  · nsys 없음 (커널 순서 항목만 포기, 본 실험은 가능)')
print('=' * 74)
OUT['verdict_go'] = go
p = Path(f'gpu_probe_{socket.gethostname()}.json'); p.write_text(json.dumps(OUT, indent=2, default=str))
print(f'\n저장: {p}   (로컬로 가져와서 gpu02_analyze.py 에 넣는다)')
sys.exit(0 if go else 1)
