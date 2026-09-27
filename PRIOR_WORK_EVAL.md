# 인접 논문의 평가 방법 해부 — 우리가 맞춰야 할 평가 바닥선

작성 2026-09-20. 논문 A(3D SRAM 기술 설계공간 논문)의 평가 설계를 정하기 위해, 인접 논문 4묶음의 모델·배치·문맥·trace·시뮬레이터·베이스라인·지표·3D 메모리 가정을 뜯었다. 각 묶음은 원문(arXiv HTML/PDF)을 읽은 추출이며 "not stated"는 논문에 없다는 뜻이다. 3절(ICCAD 2025 3D chiplet)만 미완이다.

## 0. 요약: 바닥선과 우리 위치

| 항목 | 커뮤니티 바닥선 (6/6 또는 5/6 논문) | 차별 요소 (일부 논문) | 우리 현재 |
|---|---|---|---|
| GPU 베이스라인 | A100 40/80 GB 8장급, 또는 H100. 대부분 피크 스펙에서 모델링 | 실측 vLLM 베이스라인(CENT), PyTorch 실측(NeuPIMs) | **B200 실측, vLLM 0.28.0** (바닥선 초과) |
| 모델 | 70B급 + 175B급 2종 이상, MoE는 2/6 | 7~13B, Mamba 하이브리드(HYDRA) | 7~8B dense 4종 + hybrid + MoE 2 + 27B (70B·175B 없음) |
| 배치·문맥 | 배치 32~128, 문맥 (128~4096)² 격자 또는 4K 고정 | 32K(CENT), 배치 512 | **B 1/8/32, N 2K/8K** (배치 상한 낮음) |
| trace | 합성 고정 길이가 다수. ShareGPT 3/6 | Azure LLM trace(3DLS·LaMoSys), LMSYS-Chat-1M(HYDRA), MT-Bench 라우팅(HD-MoE) | 고정 길이 자체 실행, prefix cache 끔 (trace 없음) |
| 시뮬레이터 | Ramulator/Ramulator2 4/6, DRAMsim3, Timeloop/Accelergy | HotSpot 열(Tasa), ATSim3.5D(LaMoSys), 분석 모델(HD-MoE) | 구조식 트래픽 계산기 + 실측 앵커 2파라미터 회귀 (사이클 시뮬 없음) |
| 메모리 파라미터 출처 | 하드웨어 계열: HBM3 JEDEC 타이밍, pJ/bit 인용(0.66~0.88 SeDRAM), CACTI/FinCACTI, ASAP7. **정책 계열은 fast tier 지연을 4/4가 미기재** | 테이프아웃 보정(LaMoSys, Expert Streaming) | 소자팀 n5a 모델(자기정의 룰) + 용량·BW·열 상한. E/bit 미수신 |
| 지표 | tokens/s 6/6, 에너지 5/6, 면적 5/6, prefill/decode 분리 | p99 TBT(Duplex), TCO(CENT), 온도(Tasa·LaMoSys) | step 시간·W·tokens/s·J/token 실측(B200), 트래픽 바이트 |
| 검증 | 대부분 "not stated" | DGX 실측 대조(AttAcc, 오차 미기재), ASTRA-sim 대조(HD-MoE) | 앵커 3~4점 회귀 오차 ≤ 2%(dense) |

읽는 법: 우리가 바닥선을 넘는 곳은 실측 GPU 베이스라인 하나다. 부족한 곳은 70B급 모델, 배치 ≥ 64, 실제 trace(ShareGPT·Azure), 사이클 수준 메모리 모델, HBM·티어 pJ/bit 출처다. 논문 A의 평가 계획은 이 다섯을 채우거나 명시적으로 범위 밖으로 둔다.

## 1. PIM/NMP 메모리 시스템 논문 6편 (ASPLOS·MICRO·ICCAD)

| 논문 (학회, arXiv) | 도구 · GPU 베이스라인 | 메모리 파라미터·출처 | workload | 베이스라인 | 지표 | 헤드라인 (대비) | 민감도 |
|---|---|---|---|---|---|---|---|
| AttAcc! (ASPLOS'24; DOI 10.1145/3620665.3640422) | Ramulator 수정 자체 시뮬. GPU는 피크 스펙(2.5 PFLOPS, 26.8 TB/s). DGX A100 실측 대조(OPT-66B), 오차 미기재 | HBM3 5.2 Gbps/pin, 40 스택, 640/1,280 GB; 내부 242 TB/s; HBM 에너지 [43]; ASAP7; FinCACTI | LLaMA-65B FP16, GPT-3 175B FP16, MT-NLG 530B INT8; (L_in, L_out) ∈ {128, 512, 2048}²; 배치 = 용량/SLO 최대; 합성 평균 길이 10,000 요청; 생성 단계 중심 | DGX_Base/Large/CPU, 2×DGX | 정규화 시간·throughput, mJ/token, EDAP, 면적 | 3.49×/3.91×/5.93× vs DGX_Base; 에너지 −66% | 길이, 모델, SLO, FP16/INT8, PU 배치 |
| NeuPIMs (ASPLOS'24; 2403.00579) | ONNXim + 자체 PIM 시뮬(DRAMsim3). GPU-only는 A100 40GB PyTorch 실측. 검증 미기재 | HBM 32 ch × 1 GB, 타이밍표; Micron 전력 모델; CACTI 7.0 22 nm | GPT3-7B/13B/30B/175B; 배치 64~512; ShareGPT(80/296), Alpaca(12/56); 양 단계 | GPU-only, NPU-only, NPU+PIM, TransPIM | throughput, 이용률, mW, 면적 3.11% | 3×/2.4×/1.6× | 배치, 모델, 구성 ablation |
| Duplex (MICRO'24; 2409.01141) | Ramulator 사이클 정확; H100급 xPU는 **시뮬**. 검증 미기재 | HBM3 타이밍; 16 GB/스택; Logic-PIM 4× BW; FinCACTI; 7 nm PDK | Mixtral 47B, GLaM 143B, Grok1 314B, OPT 66B, Llama3 70B; FP16; 배치 32~128; (256,256)~(4096,4096); 합성, Poisson QPS 4~16; 균등 라우팅; 연속 배칭 | H100, 2×GPU, Bank/BankGroup-PIM | tokens/s, T2FT, TBT p50/p90/p99, E2E, 에너지, EDAP, 면적 14.71% | 최대 2.67× throughput, −42% 에너지 vs GPU | 배치, 길이, 모델, QPS, Op/B |
| CENT (ASPLOS'25; 2502.07578) | Ramulator2 수정 + 기능 시뮬. GPU **실측**: 4× A100 80GB NVLink, vLLM, 배치 128, nvidia-smi 전력 | GDDR6-PIM 32 CXL 장치, 512 GB, 512 TB/s; Micron 전력 계산기; 19.0 mm² 7 nm; 32.4 W/장치 | Llama2 7B/13B/70B BF16; 512 prefill + 3584 decode; 배치 128(GPU)/32~80(CENT); ShareGPT 일부 | 4×A100, CXL-PNM, AttAcc, NeuPIMs | tokens/s, 지연, tokens/J, TCO | 2.3× throughput, 2.9× 에너지, 5.2× tokens/$ | 배치 4~128, 문맥 4K~32K, 장치 16~128 |
| Tasa (ICCAD'25, DOI 10.1109/ICCAD66269.2025.11240805; 2508.07252) | AttAcc 프레임워크 + Timeloop + Accelergy + Ramulator 2.0 + HotSpot 6.0; GPU 시뮬 | 4 DRAM 다이, 48 GB/스택, 6 TB/s/스택, 768 뱅크/다이; 0.66 pJ/bit [18]; ASAP7; 열 표 | LLaMA-65B, GPT-3 66B; FP16; 배치 32; (512,512); ShareGPT; Poisson QPS; decode 중심 | 8×A100 40GB, 8×A100+AttAcc, Homo-3D | throughput, 지연, 에너지 효율, 피크 온도·기울기, 면적 | 2.85×/2.21× vs GPU/GPU+PIM; 최대 −9.37 °C | 코어 수, 주파수, P:E 비, BW 공유 |
| HD-MoE (ICCAD'25; 2509.09420) | 분석 지연 모델 + 이산 사건 NoC 시뮬; ASTRA-sim 대조(673 vs 668 µs); **GPU 베이스라인 없음** | 하이브리드 본딩 3D NMP; 노드 2.5/5/10 TFLOPS, 75/50/25 GB/s; 메시 4×4~8×8; 용량·에너지 미기재 | Mixtral-8x7B, DeepSeek-V2-Lite, Qwen2-57B-A14B; MT-Bench 라우팅 trace; 배치 512; decode TBT | TP, EP, 하이브리드 | 정규화 TBT | 1.1~1.8× vs TP | 노드/링크 균형, 메시, 구성 |

DAC 2025의 AttenPIM(DOI 10.1109/DAC63849.2025.11133230)은 접근 불가(ACM 403)라 미추출.

## 2. 3D 적층 LLM serving 논문 4편

| 항목 | Tasa (2508.07252) | 3DLS (2607.01617, IEEE CAL 2026) | LaMoSys3.5D (2512.08731) | HYDRA (2608.19395, CASES 2026/TCAD) |
|---|---|---|---|---|
| 하드웨어 | 이종 로직 다이(P/E 코어 48~72, 1 GHz) 아래 하이브리드 본딩 DRAM 4다이; 8장치 TP | 로직-온-로직 2티어(prefill 위, decode 아래), KV 수직 전송, HBM 하단 | 3.5D: HB DRAM + 7 nm 로직 chiplet + 2.5D 인터포저; prefill 5 + decode 4 chiplet | chiplet DSE 프레임워크(MARCA + TSTC + HBM3), 2D 메시 인터포저; 3D 적층 없음 |
| 적층 티어 용량/BW/지연/에너지/본딩 (출처) | 48 GB/스택, 6 TB/s/스택(128 IO/뱅크 @500 MHz), tRC 45.3 ns 등(Table I, 출처 없음); 0.66 pJ/bit [18]; SeDRAM 0.88 pJ/bit, HB 3 µm 피치 | HBM 3.35 TB/s(용량 미기재); 수직 UCIe-3D급 512 GB/s; 지연·pJ/bit 미기재 | PC 32 GB/10.6 TB/s/546 mm²/438 W, DC 64 GB/26.2 TB/s/584 mm²/638 W; ~0.7 pJ/bit 22 nm; CACTI-3DD를 테이프아웃에 보정 | HBM3 벤더 스펙(896 GB/s/스택); D2D 256~640 GB/s; 22 nm 스케일 |
| 열 모델 | HotSpot 6.0, TIM/TSV/Si 파라미터, 히트싱크 0.1 K/W, 85 °C에서 DVFS | 없음(200 W/cm² 1차 확인만) | ATSim3.5D 수정, 액체 냉각, 45 °C 주변, 95 °C 이상 리프레시 스로틀 | 없음(future work) |
| 도구 · GPU 보정 | AttAcc + Timeloop + Accelergy + Ramulator 2.0 + HotSpot; 보정 미기재 | trace 기반 자체 시뮬; 검증 미기재 | SimPy 이산 사건 + 분석 LUT; DistServe/GenZ 방식; GPU 대비 오차 미기재 | 자체 이산 사건 시뮬; 자기 완전탐색 대비만 검증 |
| workload | LLaMA-65B, GPT-3 66B; ShareGPT; 배치 32, (512,512); Poisson QPS | LLaMA3-8B/70B, OPT-175B; Azure Conv/Code trace | GPT-13B, QwQ-32B, LLaMA3-70B; Azure Code, DeepSeek-R1 합성, LongBench; 200 요청; 1/2/4 req/s | Nemotron-H-4B, LLaMA3-7B, Mamba-2.8B; LMSYS-Chat-1M 등; 배치 2~64 |
| 베이스라인 | 8×A100 40GB, +AttAcc, Homo-3D | Naive/PM-Planar, iso-BW; GPU 없음 | A100 6×4장(시뮬), TPUv4, TETRIS, 3D-TokSIM, 3D-LC | 정적 매핑, FCFS, work-stealing |
| 지표 | 피크 온도, throughput, tokens/s/W, 지연 vs QPS | E2E, req/s, TBT | tokens/s/W, throughput, TTFT, TBT, E2E, 에너지, EDP, 면적, 전력, 온도 | tokens/s, TTFT, 이용률, DSE 시간 |
| 헤드라인 | 2.85× vs A100, 2.21×(초록)/2.12×(본문) vs A100+AttAcc | vs Naive ≤60.2% E2E 감소, 기하평균 1.22× | 0.75 tokens/s/W vs A100 0.46; TTFT는 A100보다 2.13× 나쁨 | 1.55× throughput, −43.7% TTFT |
| 민감도 | 코어 수, 비율, 주파수, 배치/길이, QPS; **용량·BW·적층 높이 sweep 없음** | KV 부하 5구간; 용량·BW·열 없음 | chiplet 용량 vs BW Pareto, NoC/NoP BW, DRAM 층수 | D2D BW, 배치, chiplet 수 |
| 인정한 한계 | 없음(DVFS 오버헤드·플로어플랜 "orthogonal") | 적층 오버헤드·수율; 면적·전력·온도 수치 없음 | TTFT 큐잉; HW 검증·비용 없음 | 전력·열·신뢰성 미모델 |

관찰: 3D 적층 논문 중 **용량 × 대역폭을 축으로 sweep한 논문은 LaMoSys3.5D(chiplet 용량 vs BW Pareto)뿐**이고, 열을 실제 도구로 넣은 것은 Tasa와 LaMoSys 둘이다. 우리 논문 A의 Fig.3(용량 × 대역폭 지도)과 Fig.5(열·패브릭 제약)는 이 공백을 정확히 겨눈다. 대신 이들은 모두 70B~175B 모델과 실제 trace(ShareGPT, Azure)를 쓰므로 우리도 최소 하나의 70B급과 하나의 공개 trace를 넣어야 같은 표에 설 수 있다.

## 3. ICCAD 2025 3D chiplet 계열 (H3D-LLM, A3D-MoE, 3D-MoE)

미추출. HD-MoE는 1·2절에 있다. H3D-LLM(IEEE Xplore 11240702)은 초록 수준만 확인했다. A800 대비 8.4× 속도·12.3× 에너지 효율(Llama-7B)을 주장하며, 평가 도구·trace·베이스라인 취득 방법은 원문 접근이 필요하다. IEEE Xplore가 막혀 있어 저자 사본이나 도서관 접근이 필요하다.

## 4. 배치 정책 계열 4편 (fast tier에 무엇을 둘지)

| 논문 | 무엇을 어디에 (fast tier 파라미터) | 도구·검증 | workload | 베이스라인 | 지표 | 헤드라인 | 민감도 | 인정한 한계 |
|---|---|---|---|---|---|---|---|---|
| Cache-Resident LLM Inference (2606.25353) | INT8 weight를 weight 소켓 LLC에 상주, KV·attention은 별도 소켓. LLC 1,152 MB/소켓(AMD EPYC 9684X). **LLC 대역폭·지연·에너지 미기재** | **실 하드웨어** 4노드 dual-socket EPYC + RDMA, 자체 런타임. 분석 TPOT 모델이 실측의 1.15~1.52× | Llama-3.2-3B, Llama-2-7B 실측; Qwen3-8B, Llama-2-70B는 모델만. INT8. 배치 1~32, 문맥 1,024~4,096. **decode/TPOT만** | 동일 프로비저닝 llama.cpp. 정책 베이스라인 없음 | TPOT, tokens/s, 블록별 지연. 에너지 없음, 정확도는 출력 일치만 | llama.cpp 대비 TPOT 2.04~11.51×(문맥 4,096) | 배치 × 문맥 격자, 4모델, 스레드풀, 소켓 분리. **용량·BW sweep 없음, trace 없음** | E2E는 7B 이하; prefill·TTFT·연속 배칭·MoE·에너지·정확도 미평가 |
| Dynamic KV Placement (IEEE CAL 2025; 2508.13231) | KV를 토큰 단위로 HBM vs off-package DRAM에 배치, weight는 HBM 고정. HBM 4.9 TB/s·24 GB, DRAM 링크 900 GB/s·DRAM 500 GB/s·480 GB (GH200 기반). 지연·에너지 미기재 | **행동 시뮬레이터**, step = bytes/BW의 max. 하드웨어 검증 없음 | LLaMA-3.1-8B; NarrativeQA(LongBench) 약 30k 토큰 프롬프트, 10K decode. 배치 미기재. decode만 | 정책만: Unlimited HBM, Static, Reactive LRU, page 단위 oracle, SA-guided oracle(제안) | 정규화 tokens/s, HBM 적중률, decode 지연 | Static 대비 최대 5.87× | attention sparsity sweep. **용량·BW·배치 sweep 없음** | **oracle이라 배포 불가**를 명시. 단일 모델·데이터셋, 대역폭만의 모델 |
| AVMP (2605.22416) | KV page와 SSM 블록을 하나의 가상 핸들 공간 뒤 두 VRAM 풀로. **대역폭 티어가 아니라 같은 VRAM 안의 용량 분할**. 풀 1/4 GiB, RTX 3060 | **순수 Python 할당기 + 합성 trace**, forward pass 없음. 실제 엔진 대비 미검증 | jamba_1_5_mini, mamba2_1b3. 180셀(5변형×3워크로드×2스펙×2풀×3시드) + ShareGPT-Vicuna 5,000 프롬프트. prefill/decode 미분리 | vLLM padded_unified, SGLang fixed_dual(mr 0.5/0.9), 자체 static | OOM 수, goodput, 유효 배치, 벽시계, 피크 VRAM, 부트스트랩 CI. **TTFT/TPOT·정확도·BW·에너지 없음** | fixed_dual_mr05 대비 goodput 1.83~13.30×, ShareGPT 2.36×. 이득의 대부분이 가상 계층이지 재배치가 아님을 스스로 분리 | migration batch 1~256, 임계값(널 결과) | 2× VRAM 사용, Python, 단어수 토큰 근사, 합성 도착, 단일 GPU. 스스로 "검증할 가설" |
| Expert Streaming FSE-DP (2603.27624) | MoE expert 마이크로 슬라이스를 off-package DDR에서 chiplet SRAM으로 스트리밍, UCIe D2D 순환. DSE가 다이당 14 MB 고정(>60% 이용률에 ≥16 MB + 48 GB/s DDR 필요). D2D 288 GB/s, FDI 4.02 ns, 5nm 테스트칩 | **사이클 정확 시뮬 + 테이프아웃 2×2 5nm 칩의 RTL 스케줄러**로 DSE 시뮬 보정. 시뮬 대 실리콘 오차 미기재 | Phi-3.5-MoE, Yuan2.0-M32, DeepSeek-MoE, Qwen3-30B-A3B. Wikitext-2, C4. 토큰/iter 16~1,024, 100 iter | EP, Hydra(DAC'25). ablation A1~A5. **GPU 베이스라인 없음** | MoE 층 지연, 이용률, 온칩 MB, E2E throughput. 면적 ≤30 mm²/die, <60 W 제약 | 1.22~2.00×, 온칩 메모리 최대 78.8% 절감 | **버퍼 vs DDR BW, DDR vs D2D BW, 마이크로슬라이스 수, 2×2→4×4** | D2D 링크 효율 필요, attention은 기본 head-parallel, 에너지·정확도·실리콘 E2E 미평가 |

관찰 세 가지.

1. **이 계열의 fast tier 파라미터는 우리보다 허술하다.** 네 편 모두 지연을 적지 않고, 세 편은 에너지도 적지 않는다. Dynamic KV는 대역폭만으로 step 시간을 만든다. 우리가 소자팀에서 받는 용량·대역폭·열 상한은 이 계열 기준으로는 과할 정도로 구체적이다. 반대로 말하면 **우리의 차별점은 fast tier를 실제 소자 모델에 앵커한다는 것**이고, 이는 논문 A의 spec-target 구조와 정확히 맞는다.
2. **정책 논문은 oracle과 상한을 당당히 쓴다.** Dynamic KV의 헤드라인 5.87×는 접근을 미리 아는 oracle이고 본문에서 배포 불가를 명시한다. 우리 G1(이상 용량 캐시)도 같은 등급의 상한이므로, 라벨만 정확하면 사용에 문제가 없다.
3. **AVMP는 이득의 출처를 스스로 분해했다.** 가상 계층 2.48× 대 재배치 추가분. 우리도 논문 A 마지막 절에서 "범용 캐시 대 객체 인식 배치"를 같은 방식으로 분해해야 한다.

## 5. 출처

- 묶음 1: https://scale.snu.ac.kr/papers/2024-04-Conference-ASPLOS-AttAcc.pdf · https://arxiv.org/html/2403.00579v3 · https://arxiv.org/html/2409.01141 · https://arxiv.org/html/2502.07578v3 · https://arxiv.org/html/2508.07252v3 · https://arxiv.org/html/2509.09420
- 묶음 2: https://arxiv.org/abs/2508.07252 · https://arxiv.org/abs/2607.01617 · https://arxiv.org/abs/2512.08731 · https://arxiv.org/abs/2608.19395
- 묶음 4: https://arxiv.org/abs/2606.25353 · https://arxiv.org/abs/2508.13231 · https://arxiv.org/abs/2605.22416 · https://arxiv.org/abs/2603.27624 (각 PDF 본문 대조)

---

# 6. 신규성 포지셔닝 — 주장별 선행 지도 (2026-09-21)

1~5절은 **평가 바닥선**("어떤 실험을 해야 같은 표에 서나")을 위한 정리다. 이 절은 다른 축이다 — **"무엇을 주장할 수 있나."** 장르가 아니라 **주장 단위**로 묶는다.

## 6-0. 먼저 정정 (이전 분석의 오류)

| 내가 썼던 것 | 사실 | 확인 |
|---|---|---|
| "KV 서베이는 admission을 안 다룬다" | **틀림.** Table 4 원문: *"A centralized control component decides KV placement, **admission**, eviction, or routing"* (Ownership C1). 2.3절에도 prefix-cache admission 언급 | 2607.02574 HTML 직접 확인 |
| "BEAR는 만들어진 캐시의 런타임 튜닝" | **틀림.** BEAR 는 DRAM 캐시 **아키텍처** 논문이고, **Bandwidth Aware Bypass (BAB)** 로 miss fill 을 실제로 bypass 한다 | **ISCA_2015_1.pdf 전문 확인 완료** (6-6절) |
| "weight/KV 분리를 우리가 설명한다" | **틀림.** Cache-Resident LLM이 weight 노드와 attention/KV 노드를 물리적으로 분리하며, 이유도 "static weight가 growing KV에 밀려난다"로 명시 | 2606.25353 HTML 확인 |

## 6-1. 메커니즘 축 — **여기서 주장할 것이 하나도 없다**

| 메커니즘 | 선행 | 판정 |
|---|---|---|
| 충전·probe·writeback 대역폭 회계 | **BEAR** (ISCA'15). 이상적 캐시 대비 3.8× | 상속. 싸우지 않는다 |
| selective fetch / no-allocate | **Footprint Cache** (ISCA'13), cache bypassing 문헌, dead-block prediction | 상속 |
| lifetime을 관리 축으로 | **KV 서베이 Axis B** (B0 요청 / B1 세션 / B2 세션간) | 상속. 어휘를 빌려 쓴다 |
| admission 결정 | **KV 서베이 Ownership C1** | 상속 |
| GB급 LLC weight 상주 | **Cache-Resident LLM** (EPYC 1,152 MB, 실 하드웨어) | 상속 |
| weight와 KV를 분리 | **Cache-Resident LLM** (소켓 분리) | 상속 |
| 소자 숨은 비용 ↔ 정책 co-design | **Kelle** (MICRO'25, eDRAM refresh) | 장르 선례. 인용해 위치를 잡는다 |

**결론: 메커니즘을 기여로 쓰면 전부 맞는다.** "우리가 처음"이라고 쓸 수 있는 메커니즘은 없다.

## 6-2. 기판·출력 축 — **여기가 빈칸이다**

| 논문 | 기판 | 대상 객체 | 출력 |
|---|---|---|---|
| BEAR / Footprint | 패키지 밖 적층 DRAM 캐시 | 일반 서버 워크로드 | 캐시 아키텍처 |
| Cache-Resident LLM | **기존** CPU LLC | weight + KV | 실행 구조 |
| Where Should KV Live | HBM/DRAM/SSD | **KV만** (weight 고정) | 정책 가이드 |
| Kelle | eDRAM (edge) | **KV만** | 소자+정책 co-design |
| KV 서베이 | HBM→CXL→SSD. **SRAM 없음** | **KV만** | 분류·측정 공백 |
| **우리** | **미존재 BEOL 적층 SRAM, GPU와 열 예산 공유** | **weight vs KV 경합** | **소자 스펙 역산** |

셋이 동시에 겹치는 논문이 없다. 그리고 **열 예산 공유**가 BEAR와 갈리는 물리적 지점이다 — 패키지 밖 DRAM 캐시는 compute 다이 전력 예산을 먹지 않는다.

## 6-3. 서베이가 스스로 적은 측정 공백 — 우리가 메운다

2607.02574 §5.2 원문:

> *"Eviction policies are usually described functionally but rarely measured as a control-plane cost; **no representative anchor characterizes reuse-distance distributions**, which is the strongest single piece of evidence for MG4 in §6."*

우리는 그 앵커를 갖고 있다. B200 보존 장부에서 **재사용 거리 = working set**이고 그래서 GB급 어떤 용량에서도 **LRU 적중이 정확히 0**(HBM = F+W, 바이트 일치)이다. 2026년 9월 서베이가 "이 분야에 없다"고 적은 측정을 우리가 가진 것이므로, **related work에서 이 문장을 직접 인용해 우리 위치를 잡는다.**

## 6-4. 그래서 쓸 수 있는 신규성 문장

> 우리는 cache fill 회계, bypass, weight residency, KV lifetime 중 **어느 것도 새 아이디어라고 주장하지 않는다.** 대신 아직 존재하지 않는 B200급 적층 SRAM 티어에 대해, 실측 LLM 객체 트래픽과 물리 SRAM 설계를 연결해 **어떤 allocation semantics를 노출해야 하며 그것을 지원하려면 소자를 어떻게 provision해야 하는가**를 역산한다.

```
LLM ledger + stacked-SRAM envelope + existing L2
        ↓
C, B_R, B_W, E/bit, allocation semantics      ← 출력이 정책이 아니라 스펙
```

정량 결과: 무조건 수요 충전은 **3.07 TB/s 지속 쓰기**를 요구하고 그 바이트는 정상 상태에서 한 번도 읽히지 않으며, 소자팀 20 W 예산의 **24.6%(0.2 pJ/bit) ~ 61.4%(0.5 pJ/bit)**를 소비한다. 5절이 이미 "0.5 pJ/bit면 모든 설계점이 1 미만"이라 했는데, 그 예산의 61%가 무용한 충전이다.

## 6-5. 미확인 — 쓰기 전에 반드시 읽을 것

| 논문 | 왜 위험한가 | 상태 |
|---|---|---|
| **BEAR** 원문 | fill bypass를 이미 제안했다면 우리 "selective allocation 요구"의 표현을 좁혀야 함 | 자동 추출 3회 실패. 도서관 접근 필요 |
| **MemExplorer** (2604.16007) | 이종 메모리 설계공간 합성. object-level fill/lifetime 계약이 있으면 6-2 표가 바뀜 | PDF 추출이 제목 추측 수준 |
| **Voxel** (2604.26821) | 3D 적층 + 매핑 + 열 시뮬 | PDF 추출 실패 |

세 편 모두 **사람이 읽어야** 한다. 자동 추출 결과를 신규성 판단에 쓰지 않는다.

## 6-6. BEAR 전문 확인 (2026-09-21) — 가장 가까운 선행의 정확한 경계

`ISCA_2015_1.pdf` 13쪽 전문. **피드백이 맞았다: BAB 는 존재한다.** 그런데 체제가 다르고, 그 차이가 우리 결론을 정확히 지탱한다.

**BEAR 가 실제로 하는 것.** 1 GB 적층 DRAM 캐시(Alloy Cache 기준), Bloat Factor **3.8×**(Loh-Hill 7.3×). 대역폭 팽창 셋을 분해 — Miss Probe(탐지) / **Miss Fill** / Writeback Probe. 구성요소 셋이 각각 대응: Neighboring Tag Cache / **BAB** / DCP(DRAM Cache Presence). 대역폭 32% 감소, 적중 지연 24% 감소, 성능 **+10%**.

**우리와 겹치는 것.** "충전 트래픽이 캐시 대역폭을 먹는다"와 "쓸모없는 충전을 bypass 한다"는 **전부 BEAR 가 먼저 했다.** 여기서 싸우면 안 되고, 회계 원칙을 상속한다고 명시한다.

**갈리는 지점 — 적중률 체제.**

| | BEAR | 우리 |
|---|---|---|
| 기판 | 패키지 밖 적층 DRAM 캐시 | **BEOL 적층 SRAM, compute 다이와 열 예산 공유** |
| 워크로드 | SPEC CPU2006, x86 시뮬 + USIMM | LLM decode, B200 실측 앵커 + 보존 장부 |
| **적중률** | **61 ~ 63%** | **LRU 정확히 0**, 관리 커버리지 18.6% |
| bypass 결정 | **확률 90% + Set Dueling** — 어느 라인이 죽는지 모름 | **객체 의미론** — 엔진 장부가 정확히 앎 |
| bypass 대가 | 적중률 **2%p 희생** (63 → 61%) | **희생 0** (bypass·관리 모두 18.59%) |
| guard 필요성 | bypass 가 해로울 수 있어 set dueling 으로 감시 | **해로울 수 없음** → guard 자체가 불필요 |
| 전력·에너지·열 | **문서 전체에 0회** (grep 확인) | 열 예산 24.6 ~ 61.4% 가 결론 |
| 출력 | 성능 +10% | 소자 스펙 (C, B_R, B_W, E/bit, semantics) |

**그래서 쓸 문장.**

> BEAR 는 bypass 가 적중률을 해칠 수 있기 때문에 set dueling 으로 감시해야 한다. **우리 체제에서 bypass 는 해칠 수가 없고, 바로 그 때문에 정책이기를 그치고 사양이 된다.**

**두 번째 갈림 — 전력 축이 BEAR 에 없다.** BEAR 의 논증 사슬은 대역폭 → 지연 → 성능이다. 우리 사슬은 대역폭 → **전력 → 열 예산 → 티어를 지을 가치가 있는가**이다. 패키지 밖 DRAM 캐시는 compute 다이와 전력 예산을 공유하지 않으므로 이 축이 BEAR 에 존재할 이유가 없었다. BEOL 적층 SRAM 에서는 존재한다.

**세 번째 — Bloat Factor 를 같은 단위로 비교할 수 있다.** 우리 정상 상태: 유효 적중 3.296 + 충전 13.862 = 17.158 GB/step, **Bloat Factor 5.21×**. BEAR 의 Alloy 3.8× 보다 나쁘다. 적중률이 0 에 가깝기 때문이다. 단 **우리 5.21× 는 충전만 센 값**이고 BEAR 의 Miss Probe·Writeback Probe 항이 빠져 있으므로 실제는 그 이상이다 — 이 누락을 논문에 명시한다(6-1 의 상속 항목).

**부수 발견.** BEAR 각주: 포괄적(inclusive) DRAM 캐시는 LLC 의 모든 라인을 담아야 해서 **bypass 자체가 불가능**하다. BEAR 는 이를 피하려 비포괄 설계를 쓴다. 우리 3D 티어도 selective allocation 을 지원하려면 **기존 L2 와 포괄 관계를 맺으면 안 된다** — 소자·아키텍처 요구에 이 항을 추가해야 한다. Gate 1 의 "비중복 통합" 결론과 같은 방향이고, 근거가 하나 더 생겼다.

## 6-7. MemExplorer · VOXEL 원문 확인 (2026-09-24) — "이상적 가정"을 실제로 쓴 선행

교수님 질문: "용량 C 가 전부 유용하다"는 숙제 식의 가정으로 계산한 논문이 있는가. 6-5 에서 PDF 추출
실패로 남겨 둔 두 편을 arXiv HTML·PDF 원문에서 직접 검색했다.

- **MemExplorer (2604.16007, Cambridge·Imperial·Microsoft, 2026-04, CC BY 4.0) — 있다, 그리고 가장
  가까운 선행이다.** §2.2 계층 모델이 레벨 i 에 저장된 비율 α_i 만큼은 그 레벨에서 공급하고 나머지
  (1−α_i)x 만 다음 레벨에서 가져온다(식 4). 무엇을 올릴지는 데이터 타입 우선순위(activation / KV /
  weight / equal, §4.2)로 정한다. §2.3 은 적층 SRAM 용량이 KV working set 의 상당 부분을 덮어 HBM
  대역폭 수요를 크게 줄인다고 서술한다. **교체·적중률·상주 데이터 채우기 비용은 원문 검색 범위에
  없다.** 즉 숙제 식 `HBM = D − C` 와 같은 구조다.
- **단, 대역폭 분할은 모델에 있다.** 식 (2) B_i^eff = B_i^peak − B_{i+1}^eff — 레벨이 아래에서 받으면서
  위로 보낼 때 대역폭을 나눠 쓴다. 숙제 식에 이것을 넣으면 4.22 GB 의 L2 요구가 8.49 → 14.89 TB/s,
  19 TB/s 에서의 병목 전환 용량이 11.4 → 8.4 GB 가 된다(미팅의 "C/2" 지적이 이 항).
- **우리 위치.** MemExplorer 의 가정은 틀렸다기보다 **managed residency 의 상한**이다 — 소프트웨어가
  무엇을 올릴지 정하는 NPU 에서는 거의 성립한다. 성립하지 않는 곳은 같은 식을 하드웨어 관리 캐시에
  적용할 때다(LRU −0.75 %, demand-fill 충전 13.86 GB/step). 주장: "이상적 가정은 정책이 managed 일
  때만 성립하고, 그 정책 선택이 소자 요구(쓰기 능력)까지 바꾼다."
- **VOXEL (2604.26821, UIUC) — 해당 없음.** 3D 적층 **DRAM** 칩을 트레이스 + DRAM 시뮬레이터로
  자세히 본다(행 버퍼 충돌까지). 코어 SRAM 은 다음 연산자 데이터를 미리 받는 버퍼로 쓰며 용량을 트래픽
  에서 빼는 모델이 아니다.
- 반대 방향의 선행은 여전히 BEAR(6-6): DRAM 캐시에서 이상적 캐시 대비 대역폭 3.8× 부풀림.
- **LLMCompass (2312.03134, ISCA'24) — 반대쪽 극단.** 장치 = 코어 + 공유 전역 버퍼(L2) + 주메모리, 값은
  장치 전체 하나씩(A100: 2 TB/s, 40 MB, 80 GB). 연산자를 전역 버퍼에 맞는 타일로 쪼개 매번 주메모리에서
  읽고 쓰며, 전역 버퍼는 매퍼가 명시적으로 관리한다고 보고 캐시와 스크래치패드를 구분하지 않는다.
  **스텝을 가로지르는 상주가 없으므로** decode 는 버퍼를 키워도 거의 이득이 없다고 결론낸다.
- **GenZ (2406.01698) — 장치 단위 roofline.** 플랫폼 요구를 연산량·메모리 대역폭(TB/s)·용량(GB)으로
  장치 단위로 낸다. 온칩 상주로 트래픽을 빼는 모델은 찾지 못했다.
- **포지셔닝 한 줄.** 같은 질문("SRAM 을 키우면 decode HBM 트래픽이 주는가")에 두 전통이 반대 답을
  낸다 — LLMCompass 는 ~0(상주 없음), MemExplorer 는 ≈ 용량(이상적 상주). 둘 다 정책을 변수로 두지
  않는다. 우리 replay 에서 LRU 가 전자(−0.75 %), managed residency 가 후자(18.59 %)를 재현하므로
  **"답은 정책이 정한다"**가 두 결과를 하나로 설명한다.
- **다이 단위.** 확인한 LLM 성능 모델(LLMCompass·GenZ·MemExplorer)은 모두 장치 합 기준이고, 두 다이
  사이 링크(B200 NV-HBI)를 따로 모델링한 것은 없었다. VOXEL 은 코어·NoC·뱅크 단위로 공간을 나누지만
  다이 문제가 아니라 한 칩 안의 배치 문제다.

## 6-8. "캐시 정책을 고려한 시뮬레이터"가 있는가 (2026-09-24, 교수님 새 방향 검증)

**있다.** 그래서 "기존 시뮬레이터는 캐시 정책을 안 본다"는 쓸 수 없고, 빈칸을 좁혀야 한다. 원문 확인.

| 부류 | 대표 | 캐시를 다루는 방식 | 우리와의 차이 |
|---|---|---|---|
| 사이클 단위 GPU | Accel-Sim / GPGPU-Sim | 실제 구조·정책 설정 가능 | 커널 단위 시뮬레이션. 속도 비교는 인용 가능한 절대 시간이 없어 수치로 쓰지 않는다(검색 요약의 '수백만 배'는 출처 미확인, 삭제) |
| LLM 타일 단위 GPU | **GPU-Tile-Sim (2607.11262)** | L2 = 완전 연관 **LRU 하나**, 타일 접근 → 캐시 라인 적중/미스. A100/H100 커널 MAPE ≤ 11.3 %, B200 예비. Accel-Sim 대비 3.5~4.6× 빠름 | 정책 고정, 목적은 커널 내 재사용·겹침 타이밍. 용량·정책 스윕 아님 |
| LLM LLC 마이크로아키 | **LLaMCAT (2512.00083)** | decode 용 LLC 미스 처리 중재·스로틀링, 분석 + 사이클 혼합 시뮬 | 대역폭 활용이 주제, 상주·적중 아님, bypass 명시 제외 |
| 서빙 시뮬의 SW 캐시 | LLMServingSim 2.0 (2511.07229), Frontier (2605.21312), KernelSight-LM (2606.28565) | KV/prefix 캐시를 GPU·호스트·디스크 층에 두는 정책, 연산자 시간은 프로파일 | 하드웨어 온칩 캐시 아님. KernelSight 는 "L2 residency"를 ML 특징으로만 씀 |
| 이상적 / 상주 없음 | MemExplorer / LLMCompass·GenZ | 6-7 | 정책 없음 |
| 수명 → 메모리 구성 | GainSight (2504.14866) | 사이클 백엔드로 데이터 수명을 재서 gain cell·eDRAM 구성 결정 | 캐시 정책이 아니라 소자 선택 |

**실측 근거(시뮬레이터 아님, 우리 편).** A Systematic Characterization (2512.01644): decode 에서 L2 적중률이
prefill 대비 크게 떨어짐(attention 73~82 % 감소). Async KV Prefetching (2504.06319): vLLM decode attention
커널 L2 적중률 0.12 % 실측 → KV 를 L2 에 미리 넣어 커널 1.84~2.15×. "기본 정책은 ~0, 관리하면 이득"을
실 GPU 에서 보인 선행이며 우리 LRU ≈ 0 과 일치. Cache-Resident LLM (2606.25353): GB 급 CPU LLC weight 상주.

**남는 빈칸(정확히).** 하드웨어 캐시 정책(입장·삽입 위치·보호)을 **설계 변수**로 두고, **채우기 트래픽까지**
세면서, **decode 스텝을 가로지르는 상주**를 **스윕 가능한 속도**로 예측하는 LLM 모델은 찾지 못했다.
주장 문장: "기존 LLM 성능 모델은 온칩 캐시를 (a) 스텝 간 상주 없이, (b) 이상적 상주로, 또는 (c) 고정 LRU 로
커널 단위에서만 다룬다." "더 정확"은 (a)(b) 대비로만(카운터 검증 후), GTSim 대비는 "빠르고 정책을 바꿔 볼
수 있다"까지 — 커널 타이밍은 GTSim 이 더 정밀하다.

**추가 경쟁자 — DCO / LCM (원문 확인 2026-09-24).** DCO (arXiv 2512.07312, v2 2026-09-10, IEEE 2026 저작권 표기 —
게재처는 abs 페이지에 없음). 공유 LLC 를 둔 멀티코어 LLM 가속기에서 소프트웨어의 텐서·타일 메타데이터(TMU)로
**교체(dead-block 예측 = 수명이 끝난 라인 예측), bypass, anti-thrashing** 을 설계. 사이클 정확 시뮬로 LRU LLC 대비
최대 1.90×(본문; 초록 1.80×), 겹침을 반영한 분석 모델을 사이클 시뮬로 검증, RTL 0.064 mm². **LCM (ICS 2024) 은 DCO
의 예비판**이라고 DCO 원문이 명시 — 한 계열로 본다.
- 결과: "정책을 설계 변수로 둔다"는 **단독 신규성이 아니다**(DCO 가 반례). 우리 R3 의 reclaim 도 DCO 의 dead-block
  예측이 선행이다.
- DCO 가 **안 하는 것**: 캐시 **크기·대역폭을 정하는 것**(여러 크기에서 자기 정책의 견고성만 봄, 사이클 시뮬은
  병목을 드러내려 일부러 작은 캐시), GPU·HBM 이 아니라 가속기 LLC, 대상은 FlashAttention 연산자 내·코어 간 재사용
  — decode 스텝을 넘는 weight 상주는 아님.
- **신규성 문장(갱신).** "새 캐시 관리 정책을 제안하는 대신, 정책이 실제로 만들어 내는 상주와 채우기 트래픽을
  LLM GPU 온칩 캐시의 **용량·대역폭 결정**에 1급 입력으로 넣고, 용량만 보는 모델이나 고정 LRU 모델이 **다른(틀린)
  설계점을 고른다**는 것을 보인다." 검증은 실제 GPU 의 정책 손잡이(persisting set-aside × hitRatio)로.

## 6-9. 정책형 시뮬레이터와 직접 비교 (2026-09-27)

> **이름 규칙 (2026-09-27).** R1 이상 현상의 원인 규명 실험은 **D1·D2·D2b·D3**(Diagnosis)라 부른다. 3D SRAM 물리 구현 케이스
> C1·C2·C3(셀 어레이만 BEOL / 셀+주변회로 BEOL / 보수적 footprint)와 섞이지 않게 하기 위해서다. 데이터·스크립트 파일 이름
> (`c1_setaside_order.*`, `c2_*`, `c2b_*`, `c3_*`, `c23_v3_*`, `make_c3_figure.py`)은 해시 기록 때문에 그대로 두며 각각 D1·D2·D2b·D3 에 해당한다.

**결론부터.** 공개된 GPU 시뮬레이터·모델 가운데 NVIDIA L2 persistence 를 표현하는 것은 **없다**. 여기서 persistence 란
set-aside(`cudaLimitPersistingL2CacheSize`)와 access-policy window 의 hitRatio·hitProp·missProp 이다(아래 표는 코드로 확인).
가장 가까운 선행은 NVIDIA 내부의 **AutoScratch**(Fu et al., MLSys 2023)다. L4 실리콘 대비 DRAM 트래픽 감소를 geomean 3 % 안으로
맞혔다고 보고했지만, **코드는 공개되지 않았고** 의미론은 "resident = 하드웨어가 축출하지 못함(고정)"이다.
그래서 세 가지로 나눠 비교했다.
1. 돌릴 수 있는 도구는 실제로 돌렸다: Accel-Sim, GPU-Tile-Sim L2.
2. 코드가 없는 선행은 논문에 적힌 의미론만 재구현했다: AutoScratch. MemExplorer 식 (4)와 같은 방식이다.
3. 나머지는 경계만 적었다.

| 후보 | 코드 | 표현 가능한 L2 정책 | 커널·스텝 간 L2 유지 | NVIDIA persistence | 비교 방법 |
|---|---|---|---|---|---|
| **Accel-Sim 2.0 + GPGPU-Sim 4.x** | 공개(BSD), dev d930ad6 (2026-08-26) | LRU/FIFO, 미스 시·채울 때 할당, 쓰기 정책 4종, 32 B 섹터, 세트 해시(linear/XOR/IPOLY), 파티션 해시(IPOLY-modulo 포함) | 유지(`-gpgpu_flush_l2_cache` 기본 0) | **없음.** `cudaDeviceSetLimit` 은 성공만 돌려주는 스텁이고, `cudaStreamSetAttribute`·access-policy 코드는 시뮬레이터에도 트레이서에도 없다. 할당 정책 's'(streaming)는 L1 처리량 모델링용이다. | **실제 실행.** sm_120 트레이스를 Hopper opcode 표로 읽는 1줄 패치 필요(issue #488) |
| **GPU-Tile-Sim** (2607.11262) | 공개(MIT) | 완전연관 LRU, 채울 때 삽입, 전역 bypass | DAG(커널) 하나 안에서만 | 없음 | L2 코드를 그대로 실행 (9/26, 우리 fixed_lru 와 일치) |
| **AutoScratch** (MLSys'23, NVIDIA) | **비공개** (NVArchSim 류 트레이스 시뮬 + Python 기능 L2) | 1 MB 조각별 resident 여부, resident 는 축출 불가, 나머지는 기본 교체. 상한은 set-aside (L4 36 MB) | 추론 1회 = 스텝 | **있음.** 다만 고정 의미론만 있고 hitRatio·streaming 은 없다 | **의미론 재구현** (`scripts/prior/autoscratch_pin.py`) |
| LLaMCAT (2512.00083) / DCO (2512.07312) / LCM (ICS'24) | 찾지 못함 | MSHR 중재·스로틀링 / dead-block·bypass·anti-thrashing (Ramulator2 LLC) | DCO: 배치 간 | 없음 (NPU LLC) | 비교 불가. NVIDIA 하드웨어의 예측기가 아니라 설계할 정책이다 |
| PPT-GPU / HyFiSS / GCoM / Nugteren'14 | 공개 | 재사용 거리(LRU) / 섹터 집합연관 LRU | 커널마다 초기화 | 없음 | 스텝 간 상주가 없으므로 no-residency 부류(LLMCompass)로 대표한다 |
| MacSim | 공개 | LRU/PLRU, bypass 손잡이, CPU/GPU way 분할 | 불확실 | 없음 | 제외. Fermi 세대 설정이고, NVBit 트레이서가 스스로 unstable 표기 |
| gem5-GPU (Ruby RRIP 등), MGPUSim | 공개 | RRIP·BRRIP 등 | — | 없음 | 제외 (AMD GPU 모델) |
| NVArchSim (NVAS) | 비공개 | — | — | — | — |

**마이크로벤치마크 선행.** Hopper·Blackwell 해부 논문(2501.12084, 2507.10789, 2512.02189)은 persistence 와 L2 교체를
다루지 않는다. persistence 측정은 L40(Ada, L2 96 MiB, set-aside 상한 66 MiB) 한 편(2606.22588, 시간만 잼, 카운터 없음)뿐이다.
256 MiB 냉 스트림 뒤에 hot set 16~64 MiB 는 보호되고, 72 MiB 는 부분 보호, 80~88 MiB 는 이득이 없다.
"상한을 조금 넘으면 부분 보호"라는 점은 v1(완전연관, 넘치면 전부 thrash)보다 v2(세트 단위)에 맞는 정성적 근거다.

**결과 (2026-09-27, 사전 고정 예측 + 하드웨어 카운터; 그림 `assets/figures/prior-sim-comparison.png`).** DRAM 읽기 MAE, MiB/스텝.

| 예측기 | 정책 표현 | H1c 합성 보류 150 | R1 실제 LLM 141 | R1 최적 hitRatio 선택 (15 그룹) |
|---|---|---|---|---|
| 우리 v3 (v2 + 로드 명령 클래스) | 예 + 명령어 | **4.28** (= v2, 합성엔 힌트 없음) | **9.07** (사후: 클래스를 SASS 로 정함) | 11 |
| 우리 v2 (세트 단위) | 예 | **4.28** | 21.29 | 8 |
| 우리 v1 (문서 의미) | 예 | 12.69 | **20.95** | 7 |
| AutoScratch 의미론 (재구현) | 고정만 | 15.35 | 25.76 | 7 |
| GPU-Tile-Sim L2 (실제 코드) | 아니오 | 13.39 | 27.51 | 0 |
| LLMCompass (실제 도구) / 상주 없음 | 아니오 | 24.10 | 28.54 | 0 |
| GenZ (실제 도구) | 아니오 | — | 32.77 | 0 |
| MemExplorer 식 (4) / 용량만 | 아니오 | 59.91 | 74.91 | 0 |
| Accel-Sim 2.0 (실제 실행) | 아니오 | 13.39 (6 워크로드 모두 완전연관 LRU 와 같은 값) | 23.11 (135M B1·B8 의 94 설정만; 같은 94 설정에서 GPU-Tile-Sim 23.08) | 0 (94 설정의 10 그룹) |

**R2 — v3 의 사전 검증 (처음 보는 실제 디코드 6 워크로드, 282 설정, 모든 예측을 측정 전에 고정; 그림 `assets/figures/r2-prospective.png`).**
로드 클래스는 측정 전에 각 워크로드의 SASS 에서 정했다(배치 1 = cuBLAS gemvx `LDG.E.EF`, 배치 ≥ 2 = CUTLASS GEMM 일반 로드).

| 예측기 | R2 MAE (MiB/스텝) | 5 % 이내 | 정책 반응 상관 | 최적 hitRatio 선택 (30 그룹) |
|---|---|---|---|---|
| **우리 v3 (사전 고정)** | **7.51** | **97 %** | **+0.95** | **30** (추가 손실 0.9 MiB) |
| 우리 v2 | 13.58 | 82 % | +0.55 | 24 |
| 우리 v1 | 13.61 | 82 % | +0.56 | 19 |
| GPU-Tile-Sim L2 | 19.00 | 72 % | 0 | 0 |
| AutoScratch 의미론 | 25.97 | 52 % | +0.02 | 17 |
| MemExplorer 식 (4) | 82.00 | 4 % | 0 | 0 |

사전 진술 넷 중 셋은 통과했다. set-aside 대비 진술은 6 워크로드 중 5 개가 통과했고, 1 개(360M B1 c1536, +37.5 vs v3 27.1 ± 10)는
0.4 MiB 차로 실패했다. 이 실패도 그대로 보고한다. 같은 모델이라도 배치 1 에서 2 로 가면 set-aside 효과가 되살아난다
(135M: +7.0 → +35.8). SASS 로 정한 로드 클래스가 이 전환을 측정 전에 맞혔다. v2 는 모든 워크로드에서 +36 을 예측했다.
남은 체계적 오차는 셋이다. ① 모델 밖 트래픽 +5~8 MiB. ② E 워크로드에서 hitRatio 0.4~0.5 부근의 이른 오르막.
③ N 워크로드에서 문서 권장(창 = S, r 1)이 v3 보다 더 아낀다.

**R3 — 개입: 커널 로드 방식을 바꾸면 (2026-09-27 17:31~19:15, 188 설정, 모든 예측을 측정 전에 고정; 그림 `assets/figures/r3-intervention.png`).**
R2 의 배치 ≥ 2 워크로드 네 개에서 디코드 투영의 가중치 로드만 `ld.global.cs`(SASS `LDG.E.EF`)로 바꾼 커널을 썼다
(`scripts/gpu/cs_linear*`). v3 는 가중치 클래스만 E 로 바꿔 예측했고, 로드 클래스를 못 보는 예측기는 개입 전과 같은 값을 낸다.

| 예측기 | R3 MAE (MiB/스텝) | 5 % 이내 | 정책 반응 상관 | 최적 hitRatio 선택 (20 그룹) |
|---|---|---|---|---|
| **우리 v3 (사전 고정)** | **8.97** | **89 %** | **+0.96** | **20** |
| 우리 v1 | 19.65 | 61 % | +0.39 | 9 |
| 우리 v2 | 19.87 | 61 % | +0.40 | 11 |
| GPU-Tile-Sim L2 | 27.03 | 56 % | 0 | 0 |
| AutoScratch 의미론 | 28.45 | 44 % | −0.08 | 8 |
| MemExplorer 식 (4) | 72.12 | 1 % | 0 | 0 |

사전 진술 넷이 모두 통과했다. 워크로드별 기준선 변화(실측 / v3)는 −25.7 / −22.6, −44.3 / −45.2, −68.6 / −75.0, −2.5 / 0.0 MiB 이다.
set-aside 대비 S12 − S60 은 개입 전 +36~40 에서 +2.3 / +21.0 / +37.3 / +38.8 이 되었고, v3 예측은 +0.0 / +12.8 / +35.0 / +36.1 이다.
KV 가 L2 에 들어가는 정도에 따라 개입 효과가 사라지고(360M B8, KV 160 MiB) 남는(135M, 360M B4) 양상을 측정 전에 맞혔다.
결정도 바뀐다. 135M B4 의 최적 set-aside 는 60 에서 36 MiB 로 줄고, 360M B4 는 창 없이 set-aside 만 두는 것이 최적이 된다.
정직하게 적을 것은 둘이다. 360M B4 에서는 r 0 창이 +11 MiB 를 늘리는 것을 v3 가 보지 못했다(창 streaming ≠ `.cs`). 360M B8 에서는
권장식을 16 MiB 과대예측했다. 그래서 두 워크로드에서 v3 가 고른 설정이 전 격자 최적보다 스텝의 2 % 안쪽만큼 나쁘다.

**N1 — 음성 대조: 작업집합이 L2 의 35~38 배인 모델 (2026-09-27 19:59~20:07, 18 설정, 예측 sha db5891a8 측정 전 고정).**
SmolLM2-1.7B 배치 1·4, 문맥 512. 사전 진술 셋이 모두 통과했다.

| 예측기 | B1 MAE (MiB) | B4 MAE (MiB) | 스텝 대비 (18 설정) |
|---|---|---|---|
| **우리 v3** | **13.3** | **13.8** | **0.39 %** |
| 우리 v2 | 25.0 | 13.8 | 0.56 % |
| 우리 v1 | 23.7 | 16.6 | 0.58 % |
| GPU-Tile-Sim L2 | 35.5 | 19.1 | 0.79 % |
| AutoScratch 의미론 | 29.2 | 27.2 | 0.81 % |
| MemExplorer 식 (4) | 63.2 | 97.2 | 2.27 % |

정책에 따른 실측 폭은 스텝의 1.83 %(B1)·1.63 %(B4)다. v3 는 이 영역에서도 가장 가깝다. evict-first 가중치 때문에 K 캐시 일부가
다음 스텝까지 남는 것까지 맞혔다(기준선 − 논리 스텝: 실측 −52.7, 예측 −48.3 ± 20). 그러나 모든 예측기가 스텝의 2.3 % 안이다.
**정책 인지가 결정을 바꾸는 것은 WS/L2 ≈ 1~10 배(R1~R3)에서이고, 35 배 이상에서는 어느 도구를 써도 같다.** 논문의 적용 범위를
이 음성 대조로 긋는다.

- **Accel-Sim 은 실제 디코드에서도 완전연관 LRU 와 같다.** 스텝당 DRAM 읽기 예측이 135M B1 267.82 MiB(GPU-Tile-Sim 267.81),
  135M B8 346.57 MiB(346.75)로 0.2 MiB 안에서 같다. 두 스텝 모두 같은 값이라 정상상태다. 같은 94 설정의 MAE 는 Accel-Sim 23.11,
  GPU-Tile-Sim 23.08, LLMCompass 24.02, AutoScratch 의미론 25.21, 우리 v1 17.97, v2 18.13, v3 9.43(사후)이다.
  135M B1 의 기준선(정책 없음)을 10.7 MiB 과대예측하는 것도 LRU 와 같다(실측 257.15). cuBLAS gemvx 의 `LDG.E.EF` 가중치 로드를
  일반 로드로 처리하므로, 가중치가 먼저 쫓겨나 KV 가 L2 에 남는 효과를 보지 못한다. 사이클 수준 시뮬레이터라도 정책과 명령어
  우선순위를 표현하지 못하면 DRAM 바이트에서는 단순 LRU 이상의 정보를 주지 못한다. 360M B1 은 비용(트레이스 수 시간 + 시뮬레이션
  약 1 일) 때문에 돌리지 않았다.
- Accel-Sim 비용: 워크로드마다 2 스텝(워밍업 1 + 예측 1) 시뮬레이션에 합성 0.5~3.9 시간(72~288 MiB/스텝, slowdown 762 만 배),
  실제 디코드는 135M B1 7.2 시간·B8 5.3 시간(slowdown 278 만·185 만 배)이다. 트레이싱도 실제 디코드 2 스텝에 89~97 분이 걸린다.
  우리 모델은 141 설정 전체를 수 초에 낸다. 참고로 Accel-Sim 의 스텝 시간(커널 합)은 4.66·5.19 ms 로 실측 2.65·3.43 ms 의
  1.76·1.51 배다. 설정은 3070 템플릿에 장치값만 넣은 것이라 시간은 보정되지 않았고, 이 비교에는 쓰지 않는다.
- 정책을 못 보는 도구는 한 워크로드 안에서 모든 설정에 같은 값을 내므로 정책 반응 상관이 0이고, 최적 설정을 하나도 못 고른다.
- 정책을 표현하는 선행(AutoScratch 의미론)도 **set-aside 를 보호 상한으로 보는 한** R1 에서 틀린다. 실제 디코드는 이득이 set-aside 와
  무관하다(진단 D1 로 하네스 부작용 아님을 확인). 이 약점은 우리 v1·v2 도 같다. 따라서 "정책을 고려한 모델이 더 정확하다"는
  합성에서는 크게(3배), 실제 LLM 에서는 작게(GPU-Tile-Sim 대비 24 %) 성립한다. 원인은 아래 D3 에서 로드 명령으로 밝혔다
  (하네스 순서는 D1, 커널 단위는 D2·D2b 로 기각).

**로드 명령이 정책의 효과를 바꾼다 (D3, 2026-09-27; 그림 `assets/figures/c3-load-hint.png`).** 실제 디코드의 가중치 GEMV(cuBLAS gemvx)는
sm_120 에서 `LDG.E.EF`(= `ld.global.cs`, evict-first)로 읽는다. 같은 합성 스트림(268 MiB, 창 127 MiB, r 0.4)에서 로드 방식만 바꾸면
set-aside 12/60 MiB 의 절약은 다음과 같다. 일반 로드 1 / 30 MiB. **`ld.global.cs` 55 / 55 MiB(S 무관 — R1 재현).**
createpolicy 디스크립터(evict_first·evict_last) 0 / 0 MiB, 즉 창이 무효다. 따라서 정책을 고려한 예측기는 (창, set-aside) 외에
**커널의 로드 방식**을 입력으로 받아야 한다. 선행 가운데 이를 다루는 것은 없다: Accel-Sim 은 `.EF` 수식어를 일반 로드로 처리하고
(trace_driven.cc 는 STRONG.GPU·BYPASS 만 봄), AutoScratch 의미론·GPU-Tile-Sim·LLMCompass·GenZ 에는 명령어 우선순위 개념이 없다.
우리 v3(명령어 evict-first 클래스 추가, 새 적합 없음)는 측정 전 예측으로 `.cs` 경우를 MAE 3.0 MiB 로 맞혔다(v2 14.9).
그러나 자체 디스크립터 경우는 틀렸다(21.6; 이때는 정책을 못 보는 고정 LRU 가 0.0 으로 정확). → 신규성 문장 후보:
"캐시 정책의 효과는 API 설정만으로 정해지지 않고 커널이 로드를 내는 방식과 상호작용한다. 이를 반영한 모델만 실제 LLM 디코드의
정책 반응을 맞힌다." 단 v3 의 R1 개선(21.3 → 14.3)은 사후 설명이므로 새 보류 데이터가 필요하다.

**창은 드라이버 기본 디스크립터를 단 LDG 에만 적용된다 (D3b, 2026-09-27 19:53, 사전 고정 f52e02ac; 그림 `assets/figures/load-class-window.png`).**
D3 의 자체 디스크립터 결과를 두고 두 해석을 측정 전에 고정했다. 하나는 우선순위만 본다는 해석(v3)이고, 다른 하나는 창이 드라이버
기본 디스크립터(sm_120 상수 뱅크 c[0x0][0x358])로만 전달된다는 해석(v3_desc)이다. 판정을 가르는 로드는 넷이다. createpolicy
`evict_normal`·`evict_unchanged`(우선순위는 보통인데 디스크립터를 커널이 만든 경우), TMA 벌크 복사(`cp.async.bulk`, SASS `UBLKCP`)의
힌트 없는 경우와 `evict_normal` 힌트를 단 경우다. 네 로드 모두 42 설정의 모든 창·set-aside 설정에서 창 없는 기준선과 0.1 MiB 안에서
같았다. 같은 세션의 일반 LDG 대조는 S60 r 0.4 에서 29 MiB 를 아꼈고, D2 를 0.6 MiB 차로 재현했다. MAE 는 v3_desc 0.96,
고정 LRU 6.35, v3 8.42 다. 즉 로드 클래스는 셋이다. ① 기본 디스크립터 + 일반 우선순위: 창이 적용되고 set-aside 가 상한이다.
② 기본 디스크립터 + `.EF`: 창이 적용되고 set-aside 와 무관하다. ③ 커널이 만든 디스크립터 또는 TMA: 창이 적용되지 않는다.
어느 선행 도구도 ③ 을 구별하지 않는다. 문서화된 의미론을 따르는 모델(우리 v1·v2, AutoScratch)은 ③ 에서 창의 이득을 과대예측한다.
정책을 못 보는 도구(고정 LRU)는 ③ 에서만 우연히 맞는다.

**배치가 로드 방식을 바꾼다 (2026-09-27 06:30).** 배치 1 디코드의 가중치는 cuBLAS gemvx 가 `LDG.E.EF`(evict-first)로 읽고,
배치 8 은 CUTLASS wmma GEMM 이 일반 우선순위(`LDG.E.LTC128B`, `LD.E`)로 읽는다. 그래서 같은 창·set-aside 라도 B1 은 S 와 무관하고
B8 은 S 에 민감하다. 각 워크로드의 SASS 로 클래스를 정한 v3 는 R1 MAE 9.07 MiB 이다(사후, 적합 0; 선행 최선은 AutoScratch 의미론 25.76).
이 결과가 논문의 논지를 바꾼다. "정책을 고려하면 더 정확하다"는 **정책 API 만으로는 부족하고 커널의 로드 방식까지 넣어야 성립한다.**
이 입력은 트레이스나 SASS 에서 기계적으로 얻을 수 있다(적합이 아님). 선행 시뮬레이터는 둘 다 다루지 않는다.

---

# 7. 교수님 리뷰 목록 1차 — 칩렛·STCO 시뮬레이터 2편과 결정론적 캐시 1편 (2026-09-27)

방향 전환(3D SRAM 제외, "캐시 정책을 고려한 시뮬레이터 + 카운터 검증", 6-8·6-9) 뒤 교수님이 리뷰하라고 준 목록 가운데 3편이다.
세 편 모두 PDF 전문을 읽었고, 그림 값은 쪽을 이미지로 뽑아 픽셀로 재서 본문과 대조했다.
**셋 다 GPU·LLM·L2 정책을 다루지 않으므로 6-8 의 빈칸을 위협하지 않는다.** 쓰임은 둘이다. 하나는 시뮬레이터 논문이 주장을
닫는 방식(CHIPSIM·HCS)이고, 다른 하나는 실제 하드웨어에서 소프트웨어로 캐시 상주를 통제한 선행(DMH)이다.
두 칩렛 논문은 "STCO"라는 말을 쓰지 않는다(grep). 기술(패키징·D2D·IMC 소자)과 시스템(토폴로지·매핑)을 한 도구에서
평가한다는 점에서 STCO 장르이지만, **설계점을 실제로 고르는 최적화 루프는 둘 다 닫지 않는다.**

## 7-1. 한눈에

| | CHIPSIM | Hetero-ChipletSim (HCS) | DMH (Deterministic Memory Hierarchy) |
|---|---|---|---|
| 서지 | Pfromm·Kanani·Sharma·Doppa·Pande·Ogras (UW–Madison, WSU). arXiv 2510.25958, IEEE OJ-SSCS 게재 승인 (10.1109/OJSSCS.2025.3626314). 코드 공개 | Yuan·Gu·Wu·Hu·Wei·Yin (Tsinghua). DATE 2026, 본문 2쪽 (10.23919/DATE69613.2026.11539069) | Kloda·Solieri·Mancuso·Capodieci·Valente·Bertogna (UNIMORE, BU). RTAS 2019 (10.1109/RTAS.2019.00009) |
| 종류 | 칩렛 DNN 공동 시뮬레이션 프레임워크 | 이종 칩렛·D2D·패키징 시뮬레이션 방법론 | 시뮬레이터 아님. 실 SoC 의 캐시 분할·결정적 할당 기법 + 측정 |
| 결합한 도구 | CiMLoop(연산, Timeloop/Accelergy 기반 IMC) + HeteroGarnet(NoI, 사이클 정확) + MFIT(열) + Global Manager(1 µs 전역 시계) | Verilator RTL / SystemC / C++ 칩렛을 각자 프로세스로, LinkSim(D2D 메시지 중계·지연층·에너지) + MPI | Jailhouse 하이퍼바이저 컬러링(L2 + DRAM 뱅크), SMMU, IDA |
| 캐시 정책 | **없음** (IMC weight-stationary, DRAM = 대역폭 링크) | 캐시 칩렛은 있으나 정책은 변수 아님 (모델 추상화 수준만 비교) | **핵심.** 의사 난수 교체 L2 를 invalidate-first 불변식으로 결정적으로 채움 |
| 참값 | 주 결과는 **자기 자신**(기준선과의 차이). 별도 HW 검증 한 절 | 같은 캐시의 **RTL** | **실 하드웨어** (Tegra X1, PMU) |
| 정확도 수치 | 기준선 차이 최대 340 %(동종)·632 %(이종). HW 대비 평균 0.75~2.51 %, 최대 5.74 % | C++ 기능 모델 −30.3 %(RTL 대비 평균). 지연층 추가 시 본문 "towers 2.6 %" — **그림에선 약 12 %** | Markov 모형 기댓값 10.303 줄 vs 실측 평균 10.16 줄 (16-way, 13K 회) |
| 벤치마크 | AlexNet·ResNet18/34/50 에서 무작위 50 개 스트림, 인스턴스당 추론 1~20 회. ViT-B/16. HW 검증은 층별 load-compute-store 매크로 커널 | multiply·mt-matmul·towers (riscv-tests 의 이름과 같음, 출처 미기재) | LMBench lat_mem_rd + stress(8 MiB). 합성 w-way·K 회. TACLeBench + Linux lib 5 종 × 1K 회 |
| 닫는 방식 | 기준선 오차가 활용도(추론 수)와 함께 커짐 → 이종·Floret·ViT 시연 → 전력·열 시연 → AMD Threadripper 검증 → 실행 시간 12.6 vs 12.2 분/모델 | 3축 민감도(모델 추상화·D2D·패키징) → 정성적 설계 통찰 | 효과별 마이크로벤치 → 정책의 확률 모형 검증 → 통합 실제 벤치(평균 + 최대 + L2 miss/줄) |

## 7-2. 논문별 판정

**CHIPSIM (IEEE OJ-SSCS, arXiv 2510.25958).**
- 주장: 기존 빠른 방법(SIAM·HISIM 방식)은 층마다 연산과 통신을 따로, 모델 하나씩 돌려서 (1) 층 파이프라이닝, (2) 여러 모델 동시
  실행, (3) NoI 경합을 못 본다. CHIPSIM 은 전역 시계(1 µs)로 연산(CiMLoop, 층 조각마다 스레드)과 통신(HeteroGarnet 하나가 모든
  모델의 트래픽을 맡음)을 같이 진행하고, 새 활성값이 생길 때마다 "남은 트래픽 + 새 트래픽"으로 네트워크 시뮬레이션을 갱신한다.
  연산마다 시각과 전력을 남겨 칩렛별 1 µs 전력 궤적을 만들고 MFIT 로 열을 푼다.
- 설정: 10×10 칩렛(NeuRRAM, Nature'22 파라미터. 이종은 RAELLA 칩렛 50 개를 교대로 배치), 2.5D 인터포저, 메시 XY 또는 Floret.
  모델 50 개를 AlexNet·ResNet18/34/50 에서 무작위로 뽑고 큐는 항상 찬 상태(주입률 1). 나이 문턱이 있는 순서 바꾸기를 허용한다.
  인스턴스당 추론 1/3/5/10/20 회가 파이프라이닝·활용도 손잡이다. 매퍼는 Simba 식 최근접.
- 결과: 비파이프라인에서 Comm+Compute 기준선 오차는 8~24 %로 쓸 만하다. 파이프라인에서 추론 20 회일 때 Comm only 는 AlexNet
  340 % 초과, Comm+Compute 는 AlexNet 320 %·ResNet 100~200 %. 이종 632 %(ResNet18), Floret 337 %(AlexNet), ViT-B 24~25 %.
  IMC 칩렛이 빨라서 통신이 총 시간을 지배한다.
- **HW 검증(V-F).** Threadripper PRO 7985WX(CCD 8 + IOD, GMI3 읽기 32 B·쓰기 16 B/cycle @1.733 GHz). LIKWID 로 링크 대역폭
  (CCD 당 읽기 49·쓰기 27 GB/s, 전체 270·115 GB/s)을, 마이크로 커널로 FLOPs/s 를 재서 HeteroGarnet 링크와 분석 연산 모델을
  **보정**했다. 하드웨어에서 돌린 "AlexNet" 등은 실제 DNN 이 아니라 층별 load-compute-store 시간을 흉내 낸 **매크로 커널**이고,
  CCD 마다 독립으로 돈다. 1/2/4 칩렛 시나리오의 평균 오차는 0.77 / 0.75 / 2.51 %, 최대 5.74 %(ResNet50).
- 실행 시간: 모델당 12.6 분(기준선 12.2 분). gem5 "수 주"와 표 I 의 Weeks/Hours/Seconds 는 인용값이지 측정이 아니다.
- **약점(리뷰어 관점).** ① 헤드라인 "최대 340 % 정확도 향상"의 참값은 CHIPSIM 자신이다. 기준선과의 **차이**이지 오차가 아니다.
  ② HW 검증은 그 차이를 만드는 시나리오(칩렛 간 활성값 파이프라이닝 + 여러 모델의 NoI 경합)를 재현하지 않는다. CCD 는 독립
  실행이고 통신은 CCD↔IOD↔DDR 뿐이다. ③ **결정적 실험이 빠졌다.** 기준선을 같은 HW 시나리오에 돌려 실측 대비 오차를 보인 표가
  없다. 기준선도 HW 에서 몇 % 안이라면 340 % 는 하드웨어로 뒷받침되지 않는다. ④ 보정과 검증이 같은 기계·같은 원시 연산이라
  사실상 표본 안이다. ⑤ 수치 불일치: 초록 340 %, 결론 "800 % 초과", 표 최대 632 %. ⑥ 1 µs 시간 간격의 충분성과 열 결과는 데이터
  없이 주장한다. ⑦ 캐시가 없다(IMC weight-stationary, DRAM = 대역폭 링크). 6-7 분류로는 "상주 없음" 계열이다.

**Hetero-ChipletSim (DATE 2026, 본문 2쪽).**
- 주장: 칩렛 모델의 언어·타이밍 추상화, D2D 프로토콜, 패키징이라는 세 단의 이종성을 번역 없이 한 시뮬레이션에 넣는다. 칩렛은
  각자 가장 맞는 시뮬레이터 프로세스(RTL 은 Verilator, SystemC, C++)로 두고, LinkSim 이 IPC(MPI)로 사이클을 맞추며 D2D 메시지를
  중계한다(버퍼·지연, PHY·범프·TSV·인터포저 에너지). 사이클 정확하지 않은 모델에는 "지연층"을 덧댄다. 패키징 선택(수평/수직,
  배치, 본딩)은 구성기가 LinkSim 설정으로 번역한다.
- 설정: Xeon E5-2620 v3, Verilator 5.008, OpenMPI 4.0.3. CVA6 코어 칩렛 + 오픈소스 L1 데이터 캐시 칩렛(DATE'24). 벤치
  multiply·mt-matmul·towers. D2D(UCIe·BoW·AIB)는 공개 자료값, 패키징 에너지는 Coskun et al. (TCAD'20).
- 결과(그림 3 픽셀 측정값과 본문 대조).
  - (a) C++ 기능 캐시는 RTL 대비 평균 −30.3 % (그림 −29~−31 %, 일치). 지연층(CPP-o)에 대해 본문은 "towers 2.6 %, 호스트 시간
    −12 %"라고 쓰지만 **그림은 towers 0.311 vs RTL 0.355 로 약 −12 %**다(multiply −4 %, mt-matmul 약 −9 %). RTL 대비 호스트
    시간 절감은 벤치별 약 7~13 %뿐이어서 코어 RTL 이 호스트 시간을 지배하는 것으로 보인다. 보여 준 속도-정확도 교환이 작다.
  - (b) D2D: mt-matmul 에서 BoW 2.4·AIB 2.2 vs UCIe 1.35 (정규화). 본문은 "towers 는 BoW 가 유리"라고 쓰지만 **그림은
    UCIe 0.35 < BoW 0.45 < AIB 0.87** 이다. BoW 는 AIB 보다만 빠르다(에너지는 UCIe 보다 낮다). PHY 에너지는 약 절반 이상.
  - (c) 패키징(mt-matmul, UCIe): 2.5D RDL 1.0 / 실리콘 브리지 0.79 / 수동 인터포저 0.75 / 3D 0.35~0.40. 본문 "3D 평균 1.7배"는
    그림으로는 RDL 대비 2.5~2.9배다(1.7 은 '배수 − 1'로 계산한 것으로 보인다). core-on-top TSV 에너지 1.65배는 그림과 일치한다.
- **약점.** 참값이 같은 부품의 RTL 뿐이다(실리콘·타 시뮬레이터 비교 없음). D2D·패키징 결과(3D 2.5배 등)는 가정한 지연·에너지
  값이 그대로 전파된 것이고, 패키징별 지연 파라미터의 출처가 없다. 2 칩렛·베어메탈 소형 벤치이고, MPI 확장성 시연과 열이 없다.
  본문과 그림이 세 곳에서 어긋난다.
- 우리에게: 내용은 무관하다. 인용할 만한 한 가지는 **"캐시 모델의 추상화 수준만 바꿔도 실행 시간이 30 % 달라진다"** — 캐시
  모델링 충실도가 시스템 결과를 바꾼다는 외부 근거다(단 정책이 아니라 타이밍 추상화).

**DMH — Deterministic Memory Hierarchy and Virtualization for Modern Multi-Core Embedded Systems (RTAS 2019).**
- 시뮬레이터가 아니다. 목적은 멀티코어 임베디드 SoC 에서 공유 L2·DRAM 경합과 **의사 난수 교체**로 부풀려진 WCET 를
  소프트웨어로 줄이는 것이다. 캐시 잠금은 Cortex-A9 → A15 에서 사라졌다.
- 기법: (1) Jailhouse 파티셔닝 하이퍼바이저의 2단계 주소 변환으로 페이지 컬러링(L2 + DRAM 뱅크). 색 마스크·값으로 표현하고,
  다음 색 PA 를 O(1) 비트 연산으로 구하며, 동작 중 재컬러링은 뒤에서부터 복사한다. SMMU 로 DMA 도 색 안에 둔다. (2) 부작용
  정리: L1 PIPT 색 비트와 L2 색 비트가 겹침, DMA 의 PA 직접 접근, 2단계 페이지 워크. (3) **IDA(invalidation-driven
  allocation).** "세트에 무효 줄이 있으면 교체 정책을 부르지 않고 그 줄을 채운다"는 불변식을 쓴다. 작업이 시작할 때 필요한 줄
  수만큼 clean + invalidate 하면 난수 교체에서도 자기 축출 없이 결정적으로 채워진다. 큰 작업 집합용 확장은 둘이다. 단계 경계
  무효화(컴파일러), 그리고 **메모리 타입 — 프로파일로 이득이 큰 페이지만 파티션 크기까지 cacheable 로, 나머지는 non-cacheable
  로 둔다(= 페이지 속성으로 하는 입장 제어).** 확장은 평가하지 않았다.
- 플랫폼: NVIDIA Tegra X1 (Cortex-A57, L2 2 MiB 16-way PIPT 의사 난수, 64 B 줄, L2 색 32 = 비트 [16:12], DRAM 16 뱅크, 전체
  색 64), Jailhouse 0.8, 파티션 4 개 × 코어 1, Linux 4.14.
- 평가(닫는 사다리).
  1. 컬러링: LMBench lat_mem_rd vs stress 2 개(8 MiB 순차 읽기/쓰기). 작업 집합이 파티션에 들 때 지연 최대 65.2 %(순차)·
     77.4 %(무작위) 개선. 남는 간섭은 최대 4.59 %. NVIDIA 하드웨어 프리페처가 **ARM 명세를 어기고 페이지 경계를 넘어** 색
     밖의 줄을 당겨 오기 때문이다(끄면 28 → 19 ns). 나머지 6~7 ns 는 MSHR 경합으로 추정한다.
  2. 가상화 비용: TLB 미스 지연 550 → 800 cycle (2단계 워크, 최대 7 회 메모리 접근).
  3. 난수 교체 모형: 16-way 세트에 합동 주소 16 개를 prefetch 하면 Markov 모형 기댓값 10.303 줄, 실측 평균 10.16 줄(13K 회).
     16 줄 전부 성공은 100 만 번에 한 번.
  4. IDA 합성: 작업 집합 w way (1~16), K 회 반복, 설정당 20 회. legacy 39 → 47 cycle/접근, IDA 는 약 41 로 평탄,
     IDA + prefetch 는 약 31 (−20~30 %).
  5. 통합: TACLeBench + Linux lib 5 종(Heap sort, 순차·무작위 iterator, SHA-1, Convolution), 1K 회, 파티션 64 KiB(1 색,
     "작업 집합과 맞춤"), 캐시 dirty 초기화, **HW 프리페치·분기 예측 끔**. 평균·최대 시간과 L2 miss/줄(PMU)을 보고한다. IDA 는
     miss/줄을 이론값 1 로 유지한다(iterator 기준 1.51 → 1.00, 즉 기준의 51 % 초과 미스가 난수 자기 축출이다). 간섭 아래
     컬러링만으로는 5 종 중 2 종이 부족하다.
- **약점.** 표 II 의 Heap sort "IDA+col.+interf." miss/줄 7,803.073 은 오타다(그림 7 은 약 1). 벤치가 작고 조건이
  유리하다(프리페치·분기 예측 끔). 최대값은 1K 회 관측 최대이지 WCET 분석이 아니다. 큰 작업 집합 확장은 미평가, 플랫폼은 1 종.
- **우리에게(세 편 중 가장 관련).** ① **"COTS 하드웨어의 기본 교체 정책 위에서 소프트웨어가 상주를 통제한다"와 "페이지
  속성으로 입장을 정한다"는 2019 년에 이미 있다.** '처음' 주장은 금지하고 인용으로 위치를 잡는다. 차이는 목적(결정성 vs 처리량·
  트래픽 예측), 대상(임베디드 CPU L2 2 MiB vs GPU L2 96 MiB), 형태(기법 vs 예측 모델), 손잡이(invalidate·non-cacheable 페이지
  vs set-aside·hitRatio·evict-first 로드)다. ② 검증 형식: 기제 하나를 떼어 내는 마이크로벤치 → 그 기제의 작은 확률 모형을 목표
  실험으로 검증 → 통합 실제 벤치를 시간 + 카운터로 설명. 우리 H1c → D3 → R1/R2 와 같은 사다리다. ③ **벤더의 숨은 동작을
  발견으로 보고한다**(프리페처의 명세 위반, ARMv8 암묵적 잠금). 우리 `LDG.E.EF`, 창 = 최대치에서 persistence 가 꺼짐,
  createpolicy 무효를 같은 등급의 기여로 쓸 수 있다는 선례다. ④ 반복 분포를 보고한다(13K·100K·1M 회, 1K 회의 최대). 우리
  재현성 통제(DRAM 차 0.1~0.5 MiB, WS≈L2 경계만 41.1 → 44.7 MiB, WORKLOG 9/26)를 **측정 잡음 바닥**으로 논문에 넣고 MAE 와
  나란히 둘 것. hitRatio 부여가 무작위라 경계에서는 하드웨어 자체가 흔들린다.

## 7-3. 증거 사다리 — 누가 어디까지 닫았나

| 등급 | 참값 | 해당 |
|---|---|---|
| 1 | 실리콘, 측정 전 고정한 예측, 보류 데이터, 선행 도구를 같은 설정에서 실행 | 우리 H1c (v2 4.28 MiB), R2 (사전 고정, 9/27 측정 시작) |
| 2 | 실리콘, 같은 기계에서 보정한 뒤 비교 | CHIPSIM V-F, DMH Markov 모형, 우리 R1 v3 (9.07 MiB, 사후) |
| 3 | 더 정밀한 시뮬레이터 또는 RTL | HCS (RTL), HD-MoE (ASTRA-sim, 1절) |
| 4 | 자기 자신 ("기준선이 X % 틀린다") | CHIPSIM 주 결과 (340 %·632 %) |
| 5 | 시연만 (민감도·열 지도) | HCS 그림 3(b)(c), CHIPSIM 열, 1~2절 대부분 |

## 7-4. 논문 A(정책 시뮬레이터)에 가져올 것

1. **CHIPSIM 이 빠뜨린 실험이 우리 표의 뼈대다.** 모든 선행 도구를 같은 실측 참값에 대어 오차를 낸다(6-9 표). 논문에
   "our reference is silicon counters, not our own model"을 한 문장으로 명시한다.
2. **"손잡이에 따른 오차" 곡선 (CHIPSIM 그림 6 형식).** x = hitRatio 또는 (재사용 작업 집합 / L2), y = 도구별 |오차|. 정책을
   못 보는 도구의 오차가 정책이 중요한 구간에서만 커지는 것을 한 그림에 보인다.
3. **기능 비교표 (CHIPSIM 표 I 형식)를 측정값까지.** 열 = 스텝 간 상주 · 정책 손잡이 · 로드 명령 클래스 · 카운터 검증 MAE ·
   워크로드당 시간. 체크 표시만 있는 표보다 강하다.
4. **결정 영향 절을 둔다.** 두 칩렛 논문은 STCO 장르이면서 설계점을 고르는 결과가 없다. "정책을 모르면 (용량, 대역폭)
   최적점이 바뀐다"(6-8 갱신 문장)를 보여야 시뮬레이터를 주인공으로 둔 논문이 닫힌다.
5. **벤치마크 = 주장 축을 덮는 격자.** 세 편 모두 주장이 걸린 축을 덮도록 벤치를 고른다(활용도 / 민감도 클래스 / 작업 집합
   대 파티션). 우리 축 = (재사용 작업 집합 / L2) × 로드 클래스(E/N) × 정책 손잡이. SmolLM 을 쓰는 이유를 이 비율로 정당화하고
   (DMH 의 "64 KiB = 작업 집합"과 같은 논리), 큰 모델 하나를 **음성 대조**(WS ≫ L2 에서 모든 도구가 같은 답)로 넣으면 "왜 작은
   모델인가" 질문을 미리 닫는다.
6. **피할 함정.** 사후 적합(R1 v3)을 사전 예측(R2)과 섞지 않는다. 본문 숫자는 그림과 같은 스크립트에서 생성한다(HCS 3곳,
   CHIPSIM 1곳 불일치). 인용값("수 주")을 측정처럼 쓰지 않는다.

## 7-5. 이 장르의 다른 도구 (두 칩렛 논문이 인용·비교한 것)

| 도구 | 결합 | 속도·검증 (출처) |
|---|---|---|
| gem5 + HeteroGarnet (Kite, DAC'20) | 사이클 정확 코어 + 이종 인터포저 NoC | 정확하나 느림 ("수 주", CHIPSIM 인용) |
| SIAM (TECS'21) | NeuroSim(IMC) + BookSim, 분리 실행 | 수 시간, 이종·열 없음 (CHIPSIM 서술) |
| HISIM (TCAD'25, 44권 3208쪽) | 연산·NoC·NoP 분석 모델 + 빠른 열 | 초록: 기존 도구 대비 10⁴~10⁶배 빠름. **초록에 정확도 수치 없음**(본문 미확인). 열은 층마다 정상상태 (CHIPSIM 서술) |
| RapidChiplet (arXiv 2311.06081), Switchboard (2407.20537), Metro-MPI (DATE'23), Zhi et al. (NANOCOM'21) | 칩렛 DSE 툴체인 / 모듈형 대형 HW 시뮬 / RTL MPI 분할 / 오픈소스 시뮬레이터 조합 | 미확인 (HCS·CHIPSIM 이 인용만 함) |

## 7-6. 출처

- CHIPSIM: https://arxiv.org/abs/2510.25958 (Comments: IEEE OJ-SSCS 승인, 10.1109/OJSSCS.2025.3626314), 코드
  https://github.com/LukasPfromm/CHIPSIM
- Hetero-ChipletSim: DATE 2026, 10.23919/DATE69613.2026.11539069 (사용자 제공 PDF), https://past.date-conference.com/proceedings-archive/2026/DATA/204.pdf
- DMH: RTAS 2019, 10.1109/RTAS.2019.00009 (사용자 제공 PDF)
- HISIM 초록: https://ieeexplore.ieee.org/document/10844846/ · https://asu.elsevierpure.com/en/publications/hisim-analytical-performance-modeling-and-design-space-exploratio/
