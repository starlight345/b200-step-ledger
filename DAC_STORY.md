# 논문 A: 캐시 정책은 설정값이 아니다 — LLM decode 의 GPU L2 를 정책과 로드 방식까지 넣어 예측하기

> **Beyond Capacity: Predicting LLM-Decode DRAM Traffic under GPU L2 Persistence Controls and Kernel Load Hints** (가제)

작성 2026-09-27 (Claude). 이 문서는 논문 A 의 **스토리와 주장 목록**만 소유한다. 선행 비교와 판정은 [PRIOR_WORK_EVAL.md](PRIOR_WORK_EVAL.md)
6-9·7 절, 실험 기록과 해시는 [WORKLOG_3DSRAM.md](WORKLOG_3DSRAM.md) 9/25~9/27 항목에 있다. 교수님 방향(9/24): 3D SRAM 을 빼고
"기존 시뮬레이터의 한계 + 캐시 정책 = 더 좋은 시뮬레이터". 주인공은 **통찰(정책 × 로드 방식)**이고 모델은 그 도구다.

**이름 규칙.** 실험은 H(합성, H1·H1b·H1c), R(실제 LLM 디코드, R1·R2·R3), D(원인 규명, D1·D2·D2b·D3·D3b), N(음성 대조, N1)으로 부른다.
3D SRAM 물리 케이스 C1·C2·C3 과는 무관하다.

## 한 줄 결론

GPU L2 의 persistence 손잡이(set-aside, access-policy window)가 LLM decode 의 DRAM 트래픽을 얼마나 줄이는지는 **설정값만으로 정해지지 않고,
커널이 로드를 내는 방식(일반 / evict-first / 커널이 만든 정책 디스크립터·TMA)에 따라 달라진다.** 마지막 경우에는 창이 아예 먹지 않는다. 기존 시뮬레이터(LLMCompass, GenZ, MemExplorer 식,
GPU-Tile-Sim, Accel-Sim)는 둘 다 표현하지 못해 설정을 하나도 고르지 못한다. 둘을 넣은 모델은 처음 보는 실제 디코드를 **측정 전 예측**으로
스텝의 1.7 % 오차(MAE 7.5 MiB)로 맞히고 최적 설정 30/30 을 고른다. 커널의 로드 방식을 바꾸는 개입의 결과도 측정 전에 맞힌다(R3: 네
워크로드 모두 ± 10 MiB 안, MAE 9.0 MiB, 최적 20/20). 그래서 필요한 L2 용량과 커널 설계에 대한 **결정을 바꾼다.**

## 1. 설정

| 항목 | 값 |
|---|---|
| 장치 | RTX PRO 5000 Blackwell (sm_120), L2 96 MiB, persisting 상한 60 MiB (= 10/16), 창 최대 128 MiB, DRAM 1.23 TB/s 실효 |
| 참값 | **실리콘 카운터**(ncu `dram__bytes_read.sum`, app-range, `--cache-control none`) — 우리 모델이 아니다 |
| 손잡이 | set-aside S ∈ {0, 12, 24, 36, 48, 60} MiB × 창 W (가중치 앞 127 MiB 또는 = S) × hitRatio r ∈ {0 … 1} (워크로드당 47 설정) |
| 워크로드 | SmolLM-135M / 360M 디코드 (bf16, eager, PyTorch 2.8), 배치 1~8, 문맥 512 / 1536. 작업집합 / L2 = 2.8~8.9. 음성 대조 SmolLM2-1.7B (35~38) |
| 왜 작은 모델 | 재사용 작업집합이 L2 와 같은 자릿수여야 정책이 트래픽을 움직인다. WS/L2 35~38 에서는 정책 폭이 스텝의 2 % 미만이고 모든 도구가 같은 답을 낸다(N1, 5 절) |
| 사전 등록 | 모든 검증은 예측 파일을 측정 전에 고정하고 sha256 을 WORKLOG 에 남긴 뒤 측정 (H1c, R1, R2, R3, D2·D3·D3b, N1) |

## 2. 스토리 일곱 걸음

1. **문제.** 온칩 용량이 커지고(B200 L2 126.5 MB) GPU 는 L2 정책 손잡이를 노출한다. 설계자는 "얼마나 크게, 어떻게 설정할지"를 시뮬레이터로
   정한다.
2. **기존 도구의 한계(코드와 측정).** 온칩을 (a) 스텝 간 상주 없음, (b) 용량만큼 이상적 상주, (c) 고정 LRU 로 다룬다. 정책 손잡이를
   표현하는 공개 도구는 없다. Accel-Sim 은 `cudaDeviceSetLimit` 이 스텁이고 `.EF` 수식어를 무시한다. 실측에서 이 도구들은 정책을 돌려도
   예측이 평평하고(상관 0), 최적 설정을 하나도 못 고른다.
3. **R1 의 이상 현상.** 합성(H1c)에서 맞던 세트 단위 모델 v2 가 실제 디코드에서는 크게 빗나갔다. 배치 1 에서 set-aside 를 12 MiB 로 하든
   60 MiB 로 하든 이득이 같았다.
4. **원인 규명 D1~D3, D3b.** 측정 순서 때문(D1)도, 커널 단위 때문(D2·D2b)도 아니다. **로드 캐시 힌트(D3)** 가 원인이다. cuBLAS gemv 는
   가중치를 `LDG.E.EF` 로 읽는다. 합성 커널에서 로드만 바꾸면 현상이 그대로 재현된다(개입). D3b 는 기제를 사전 예측으로 가렸다.
   창은 드라이버가 넣는 기본 디스크립터를 단 LDG 에만 적용된다. 커널이 디스크립터를 직접 만들거나(우선순위가 보통이어도) TMA 로
   읽으면 창이 아무 일도 하지 않는다(모든 설정에서 절감 0.0 MiB, v3.1 규칙 MAE 0.03 vs v3 11.2). 그래서 로드 클래스는 셋이다.
   ① 기본 디스크립터 + 일반, ② 기본 디스크립터 + evict-first, ③ 커널 생성 디스크립터 · TMA.
5. **모델 v3.** v2 에 로드 클래스를 더했다. 클래스는 적합하지 않고 SASS 에서 기계적으로 읽는다(NVBit 목록·조사). 배치 1 은 gemv(E),
   배치 ≥ 2 는 CUTLASS GEMM(N).
6. **사전 검증 R2.** 처음 보는 6 워크로드·282 설정에서 MAE 7.5 MiB(97 % 가 스텝의 5 % 이내), 최적 설정 30/30 을 골랐다.
   배치 1→2 에서 set-aside 효과가 되살아나는 것도 측정 전에 맞혔다.
7. **결정이 바뀐다.** (i) **R3 개입**: 배치 ≥ 2 의 가중치 로드를 evict-first 로 바꾸면 어떻게 되는지 모델이 먼저 예측했다. KV 가 L2 에
   들어가면 기준선이 KV 만큼 줄고 set-aside 의 영향이 줄며, KV 가 L2 보다 크면 효과가 없다. 하드웨어가 네 워크로드 모두에서 이를
   확인했다. 기준선 변화는 실측 −25.7 / −44.3 / −68.6 / −2.5 MiB, 예측 −22.6 / −45.2 / −75.0 / 0.0 이다. set-aside 대비(S12 − S60)는
   개입 전 +36~40 에서 개입 뒤 +2.3 / +21.0 / +37.3 / +38.8 이 되었고, 예측은 +0.0 / +12.8 / +35.0 / +36.1 이었다. 로드 수식어 하나가
   set-aside 결정을 바꾼다. 135M B2 에서는 set-aside 가 무의미해지고, 135M B4 에서는 최적 set-aside 가 60 에서 36 MiB 로 줄며,
   360M B4 에서는 창 없이 set-aside 만 두는 것이 최적이 된다. 기존 도구는 이 개입을 표현하지 못해 개입 전 값을 그대로 낸다
   (MAE 19.7~72.1 vs v3 9.0).
   (ii) **용량**: 20 % 절감에 필요한 L2 는 LRU 기반 도구로 약 4 배 과잉이다. 용량만 보는 도구는 정책 설정의 필요를 놓친다. 로드 방식
   하나가 필요 용량을 1.7 배 바꾼다(투영, 96 MiB 에서 실측 고정).

## 3. 주장 목록 — 네 개 (등급: 사전 = 측정 전 고정, 사후, 투영)

| # | 주장 | 근거 | 등급 |
|---|---|---|---|
| A | 기존 LLM·GPU 시뮬레이터는 L2 정책 손잡이도, 로드 우선순위도 표현하지 못한다. 처음 보는 실제 디코드에서 DRAM MAE 가 19~82 MiB/스텝이고, 정책 반응 상관이 0이며, 최적 선택이 0/30 이다(정책을 못 보는 도구) | PRIOR_WORK_EVAL 6-9 (R1·R2·Accel-Sim), 코드 확인 | 사전 (R2) |
| B | 정책의 효과는 커널 로드 클래스에 달렸다. 일반 로드면 set-aside 가 상한, evict-first 면 set-aside 무관, 커널 생성 디스크립터·TMA 면 창 무효 | D1~D3, **D3b(사전 고정 f52e02ac: ③ 네 종 모두 절감 0.0)**, SASS 조사(가중치 전량이 `LDG.E.EF`), R2 배치 전환 | 사전 (D3·D3b·R2) |
| C | 로드 클래스를 SASS 에서 읽는 정책 인지 모델(v3)은 적합 없이 처음 보는 디코드를 MAE 7.5 MiB·최적 30/30 으로 맞힌다(v2 13.6, GPU-Tile-Sim 19.0, AutoScratch 26.0) | R2 (예측 sha 8c79c377) | 사전 |
| D | 모델이 설계 결정을 바꾼다. 커널 로드 방식 개입의 효과를 미리 맞히고(R3: 사전 진술 4/4, 188 설정 MAE 8.97 vs 19.65~72.12, 최적 20/20 vs ≤ 11), 필요 L2 용량 판단이 도구마다 4 배 갈린다 | R3 (예측 sha 9635f151, 판정 `r3_verdict.json`), 용량 투영 | 사전 (R3) + 투영 |

**신규성 문장(좁혀서).** 새 캐시 정책을 제안하지 않는다(DCO·LCM 이 선행). 새 상주 최적화기도 아니다(AutoScratch 가 선행, 코드 비공개,
고정 의미론). COTS 하드웨어에서 소프트웨어로 상주를 통제하는 것도 처음이 아니다(DMH, RTAS'19 — 인용). 우리가 처음 보이는 것은 다음이다.
**GPU L2 정책 손잡이의 효과가 커널 로드 클래스와 상호작용한다는 것**, 그리고 **둘을 넣은 모델만 실리콘 카운터 기준으로 처음 보는 LLM decode 를
사전 예측하고 결정을 바꾼다는 것**이다.

**적용 범위.** 주장 A~D 는 작업집합 / L2 ≈ 2.8~8.9 인 워크로드에서 나왔다. N1(35~38 배)에서는 정책 폭이 스텝의 2 % 미만이고 모든 예측기가
스텝의 2.3 % 안에 모인다(사전 진술 3/3, 그림 6). 즉 정책 인지 모델링은 재사용 작업집합이 L2 의 한 자릿수 배일 때 결정을 바꾸고, L2 가
커질수록 그 경계가 큰 모델 쪽으로 옮겨 간다(그림 5).

## 4. 그림

| 그림 | 파일 (스크립트) | 한 줄 |
|---|---|---|
| 1 문제 | `assets/figures/prior-sim-comparison.png` (`scripts/prior/make_prior_sim_figure.py`) | 도구별 MAE (H1c·R1), 135M B1 hitRatio 반응: 실측은 set-aside 무관, 도구는 평평 |
| 2 메커니즘 | `assets/figures/load-class-window.png` (`scripts/make_load_class_figure.py`) | 로드 방식 8 종 × set-aside 12/60: ① 일반 0/29, ② `.cs` 55/55, ③ createpolicy 4 종·TMA 2 종 모두 0/0 MiB 절감, v3 vs v3.1 규칙 예측 (D3·D3b; 옛 판 `c3-load-hint.png`) |
| 3 사전 검증 | `assets/figures/r2-prospective.png` (`scripts/make_r2_figure.py`) | R2 MAE, 워크로드별 S12 − S60, 360M B1 c1536 hitRatio 반응 |
| 4 개입 | `assets/figures/r3-intervention.png` (`scripts/make_r3_figure.py`) | 개입 전·후 실측 vs v3 사전 예측: (a) 기준선 변화, (b) S12 − S60, (c) 135M B2 hitRatio 반응(개입 뒤 두 S 가 겹침) |
| 5 용량 | `assets/figures/capacity-projection.png` (`scripts/make_capacity_figure.py`) | 20 % 절감에 필요한 L2: LRU ≈ WS, 용량만 ~150, v3 188 / 320 → 191 MiB |
| 6 범위 | `assets/figures/regime.png` (`scripts/make_regime_figure.py`) | 실측 15 워크로드(R1·R2·R3·N1) × 작업집합/L2: (a) 최대 절감이 "60 MiB ÷ 작업집합" 선을 따른다(기준선에서 로드 방식이 이미 아낀 경우만 아래), (b) 예측기 간 MAE 차이는 WS/L2 < 10 에서만 크고 35 배 이상에서는 모두 스텝의 3 % 안 |
| 표 | 기능·비용 비교 | 스텝 간 상주 · 정책 손잡이 · 로드 클래스 · 실리콘 MAE · 워크로드당 시간(Accel-Sim 0.5~7.2 h vs 우리 수 초) |

## 5. 한계와 열린 항목

- **R3 (완료, 2026-09-27 17:31~19:15).** 사전 진술 4 개(기준선 변화 ± 10, S12 − S60 ± 10, MAE 최소, 최적 선택 최다)가 모두 통과했다.
  결정 수준에서는 두 워크로드에서 v3 선택이 실측 최적보다 스텝의 2 % 안쪽(15.3·14.7 MiB)만큼 나쁘다(아래 ⑤·⑩).
- **음성 대조 N1 (완료, 2026-09-27 19:59~20:07, 예측 sha db5891a8).** SmolLM2-1.7B 배치 1·4(WS/L2 35·38)에서 사전 진술 3 개 모두
  통과. 정책에 따른 실측 폭은 스텝의 1.83·1.63 %(≤ 3 %)이고, 모든 예측기의 MAE 가 스텝의 2.3 % 안이다(v3 0.39 %, MemExplorer 2.27 %).
  v3 고유 진술(기준선 − 논리 스텝 B1 −48.3 ± 20, B4 0 ± 20)도 실측 −52.7·+14.5 로 통과. 정책 인지가 결정을 바꾸는 영역은
  WS/L2 ≈ 1~10 배이고, 그 밖에서는 어느 도구든 같다 — "왜 작은 모델인가"를 데이터로 닫는다(`scripts/n1_verdict.py`, 그림 6).
- **정직하게 적을 것.** ① GPU 한 종. ② R2 사전 진술 3 은 6 개 중 1 개가 0.4 MiB 차로 실패했다. ③ v3 편향 −5.6 MiB 는 모든 모델이
  빼놓은 비가중치·비KV 트래픽이다. ④ evict-first 워크로드에서 r 0.4~0.5 의 오르막이 실측에서 더 이르다(v3.1 후보, 채택 안 함).
  ⑤ 권장식(창 = S, r 1)이 v3 예측보다 더 아낀다(R2 일반 로드, R3 360M B8 에서 16 MiB). ⑥ 자체 디스크립터 규칙(v3.1: ③ 에는 창
  미적용)은 D3b 합성 커널로만 사전 검증했다. 실제 디코드에서 ③ 커널(TMA GEMM·FA3)이 도는 GPU(H100 등)에서는 아직 재지 않았다.
  ⑦ 용량 투영은 96 MiB 에서만
  검증됐고, 창 최대치가 L2 와 비례한다고 가정했다. ⑧ R1 의 v3 개선(9.1)은 사후 값이라 본문에서 R2 와 섞지 않는다.
  ⑨ **트래픽 절감 ≠ 지연 절감(이 장치의 작은 모델).** 작은 모델 디코드는 커널 지연이 지배한다. 커널 시간은 3.1~4.4 ms 인데 DRAM 시간
  (바이트 / 1.23 TB/s)은 0.22~0.73 ms 다. 그래서 DRAM 17~19 % 절감이 커널 시간으로는 0.1~2.7 % 에 그친다. 절감한 바이트는 제 전송
  시간만큼은 아낀다(135M B2·B4 기울기 1.0~1.15 µs/MiB, 1/BW = 0.85). 대역폭이 지배하는 합성 커널(H1c clean)에서는 바이트 절감
  15~32 % 가 시간 절감 16~32 % 로 그대로 옮겨 간다(상관 +0.85~+1.00). 따라서 본문의 지표는 DRAM 트래픽이다. 트래픽은 시뮬레이터가
  지연·에너지를 계산하는 입력이고, 카운터로 정확히 잴 수 있다. 지연 이득은 "스텝 중 DRAM 시간의 몫"만큼으로 제한된다고 쓴다
  (`scripts/time_vs_bytes.py` → `assets/sweep/time_vs_bytes.json`). R3 도 같다(135M B2: DRAM 21.7 % 절감, 커널 시간 0.8 %).
  ⑩ **창의 streaming 표시 ≠ evict-first.** v3 는 창 미스 줄(streaming)을 `.cs` 줄과 같게 본다. 실측에서 r 0 인 창을 켜면 대부분
  5~13 MiB 를 아끼는데, KV 가 L2 에 거의 찬 경우(R3 360M B4, KV 80 MiB)만 +11~12 MiB 가 늘었다. 이 때문에 그 워크로드의 최적
  ('창 없이 set-aside 만')을 놓쳤다.
- **선택 보강.** 데이터센터 GPU(H200·B200) 한 대에서 D3 형 마이크로벤치 한 번(RunPod 수 달러) — 로드 클래스 상호작용의 일반성.
- **지금 하지 않을 것.** v3.1 사후 수정, 시뮬레이터 추가, 360M 급 Accel-Sim.

## 6. 재현

| 단계 | 스크립트 | 데이터 |
|---|---|---|
| 합성 H1c | `scripts/gpu/h1_run.py`, `scripts/l2policy_model_v2.py` | `assets/sweep/h1c_*` |
| 실제 디코드 R1·R2·R3 | `scripts/gpu/r1_run.py`·`r2_run.py`·`r3_run.py`, `llm_policy_bench.py`(`--weights-cs`), `cs_linear*.{py,cu}`, 판정 `scripts/r3_verdict.py` | `assets/sweep/r{1,2,3}_*`, `r3_verdict.json` |
| 시간 대 바이트 | `scripts/time_vs_bytes.py` | `assets/sweep/time_vs_bytes.json` |
| 원인 규명 D1~D3 | `scripts/gpu/c1_setaside_order.sh`, `h1_run.py` + `l2policy_bench.cu`(`hint`) | `assets/sweep/c1_*`, `c2_*`, `c2b_*`, `c3_*` (= D1·D2·D2b·D3) |
| D3b (디스크립터·TMA) | `scripts/d3b_predict.py`, `scripts/gpu/d3b_queue.sh`, `l2policy_bench.cu`(hint 4~7), 판정 `scripts/d3b_verdict.py`, 그림 `scripts/make_load_class_figure.py` | `assets/sweep/d3b_*` |
| 로드 클래스 | `scripts/prior/r2_list.sh`, `r2_census.py`, `r2_classes.py`, `asim_opcodes.py` | `assets/sweep/r2_census/` |
| 음성 대조 N1 | `scripts/n1_predict.py`, `scripts/gpu/n1_run.py`·`n1_queue.sh`, 판정 `scripts/n1_verdict.py` | `assets/sweep/n1_*` |
| 모델 | `scripts/l2policy_model_v3.py` (sha afb0e71d), `scripts/r2_predict.py`, `scripts/r3_predict.py` | `assets/sweep/r2_predictions_ampere.json` (8c79c377), `r3_predictions_ampere.json` (9635f151) |
| 선행 도구 | `scripts/prior/run_prior_tools.py`, `gtsim_l2_stream.cpp`, `asim_*.sh`·`accelsim_sm120.patch`, `autoscratch_pin.py` | `assets/sweep/r1_tool_bytes.json`, `accelsim_runs.jsonl`, `prior_sim_*` |
| 비교·용량 | `scripts/prior/prior_sim_compare.py`, `scripts/capacity_projection.py` | `assets/sweep/prior_sim_summary.json`, `capacity_projection.json` |
