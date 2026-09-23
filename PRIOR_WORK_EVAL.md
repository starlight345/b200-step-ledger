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
