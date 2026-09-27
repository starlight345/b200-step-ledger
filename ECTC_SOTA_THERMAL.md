# ECTC: 열 판정의 SOTA는 무엇이고, 우리 설계점에서 무엇을 주는가

작성 2026-09-27 (Claude). 이 문서는 교수님 질문 **"관행 식이 시뮬레이터 SOTA냐, SOTA와 비교해야 의미가 있다"**에 대한 답, 그 문헌 근거, 그리고 SOTA 관행을 우리 설계점에서 다시 돌린 결과만 소유한다. 스토리는 [ECTC_STORY.md](ECTC_STORY.md), 동기화는 [WORKLOG_3DSRAM.md](WORKLOG_3DSRAM.md).

- 계산: `scripts/sota_comparators.py` (같은 검증 솔버, 입력만 바꿈), `scripts/hotspot_rerun.py` (HotSpot 7.0 자체를 돌림)
- 결과: `assets/sweep/sota_comparators.json`, `assets/sweep/hotspot_rerun_{resolved,as-used}.json`
- 설계점: decode 듀티 4.80%, 버스트 217 µs / 주기 4.515 ms, 버스트 38 W/다이 (0.5 pJ/bit 예시값), 예산 20 W. 대역폭 = 5.0 TB/s ÷ peak fraction.

## 한 줄 결론

**관행 식은 허수아비가 아니라 지금 top-venue 논문들이 실제로 쓰는 판정이다.** LLM용 적층 메모리 논문 중 가장 최근 것들(Stratum MICRO'25의 Eq.(1), Helios·Ai et al. 2026, A3D-MoE 2025)은 "대역폭 × E_bit"를 최대 전력으로 넣은 정적 판정을 쓰고, 열을 더 신경 쓴 논문들(Tasa 2025, DeepStack MICRO'26)은 평균 전력 정상상태를 쓴다. Georgia Tech·SK hynix의 JXCDC 2025 논문은 그 가정을 문장으로 적는다: 열 시정수가 DRAM 접근 시간보다 느리니 평균 전력 프로파일을 쓴다(Sharda et al., III-A절). 우리 결과는 얇게 쌓은 다이에서 이 가정이 성립하지 않음을 보인다. SOTA **도구**(HotSpot 7, 3D-ICE 4, Icepak, Celsius)는 과도 해석을 지원하지만, 논문들이 넣는 **입력**이 정적 맵이거나 1~10 ms 간격이라 217 µs 버스트가 사라진다. 같은 V-Cache 실측 치수 스택에서 다시 돌리면 정적 최대는 **5.2배 비관**, 정적 평균은 **4.0배 낙관**, 1 ms 에폭(CoMeT)은 **2.1배 낙관**이고, 버스트를 넣으면 **25.8 TB/s**다. 패키징 표준 방법(Zth 중첩, JESD51-34, Icepak LTI ROM)에 버스트를 넣으면 우리 답이 그대로 나온다. 즉 **우리 기여는 새 열해석법이 아니라 입력(워크로드에서 유도한 버스트)과, 지금 쓰이는 판정이 같은 설계를 양방향으로 틀린다는 정량화**다.

> **주의 (2026-09-27 저녁).** 3·4절 숫자는 **이상적 뚜껑**(TIM 윗면 고정)과 **한 덩어리 버스트**를 함께 가정한 상한 코너다. 현실 패키지 경계, Gate-1 재생이 실제로 두는 배치, 매크로 주변회로 집중을 넣으면 정적 평균의 낙관은 **1.2~7.4배**, 정적 최대의 비관은 **2.8~18배** 사이에서 움직인다. 방향은 모든 경우에 유지된다. 8절 참조.

## 1. 조사 방법과 검증 상태

2026-09-26 워크플로(8개 방향 문헌 검색 → 항목별 적대적 재검증 → 누락 비판 → 종합)를 돌렸다. **결과는 절반만 나왔다.**

| 단계 | 상태 |
|---|---|
| 검색 8개 (오픈소스 도구, 상용 도구, LLM 3D 아키텍처, 패키지 열, 펄스 부하, LLM 전력, 관행 식 사용, 다이 박화) | **완료, 144건** |
| 적대적 재검증 (원문을 다시 열어 반박 시도) | **122건 중 23건만 완료**, 나머지 99건은 사용량 한도로 실패. 완료된 23건 중 반박 0, 부분 정정 16 |
| 누락 비판·종합 | **실패** (같은 이유). 이 문서가 종합을 대신한다 |

등급 표기: **V** = 1차 출처(논문 본문 또는 공개 코드)를 읽고 독립 재검증까지 통과. **P** = 1차 출처를 한 번 읽음, 재검증 없음. **S** = 2차 자료(보도, 요약)만. 관행마다 V 등급 연구를 대표로 세웠다. V가 없는 행(순간 전력밀도 상한, 럼프드 RC, 패키징 표준)은 P·S로 표시했다. **P\*** = 2026-09-27 학교 망에서 원문 전문을 직접 읽음(IEEE Xplore).

## 2. SOTA 관행 지도 — 누가 전력을 어떻게 넣나

| 관행 | 대표 연구 (등급) | 전력 입력 | 우리 버스트에 하는 일 |
|---|---|---|---|
| **정적 최대 맵** | Stratum MICRO'25 Eq.(1) `P_dram = BW × E_b` (V); Helios 2026, HotSpot-7 최대 활용 (V); Ai et al. 2026 (V); A3D-MoE 2025, Ansys Mechanical 허용 최대 전력 (V); Arm ECTC'20 maxpower 맵 (V); Sharda & Yu JETCAS'25, Ansys Mechanical에 부품별 전력밀도 할당, 최대 전력 200 W 상한 (P\*); Sharda et al. JXCDC'25, 로직 예산 220 W/cm² @ DRAM 95 °C (P\*); FGDRAM MICRO'17 Fig.1a, Keckler IEEE Micro'11, Eckert·Jayasena·Loh 2014 (P) | 최대 대역폭에서의 전력을 계속 켜 둠 | 38 W를 상시로 셈. **듀티를 전혀 인정 안 함** |
| **순간 전력밀도 상한** | VOXEL MICRO'26 논문 DSE 0.7 W/mm² (P); d-Matrix Hot Chips'26 0.5 W/mm² (S) | 순간 전력 ÷ 면적 | 버스트를 100%로 셈 (정적 최대와 같은 부류, 문턱값만 다름) |
| **정적 평균 맵** | Tasa 2025, HotSpot 6 정상상태 (V); DeepStack MICRO'26, `T = T_amb + R(m)·P`에 실행 평균 전력 (V); Sharda et al. JXCDC'25, "열 시정수가 접근 시간보다 느리다"며 DRAM에 평균 전력 (P\*); HotSpot `steady_file`·DRAMsim3 정상상태 출력은 트레이스를 평균함 (V, 소스 코드) | 듀티 × 버스트 | 1.8 W로 희석. DeepStack은 로직 349 W와 합쳐 한 노드로 푸니 티어 버스트는 0.5% 성분으로 사라짐 |
| **거친 트레이스** | HotSpot `template.config`와 예제 6개 중 5개: 10 ms (V); MFIT TODAES'25: 10 ms (V); CoMeT TACO'22, DRAMsim3 HBM2: 1 ms 에폭 (V); 3D-ICE 예제 0.2 s, PACT 예제 333 ms (V) | 구간 평균 전력 | 버스트가 구간에 퍼짐. 1 ms면 38 W가 ~8 W로 |
| **음해법 한 스텝/구간** | ATLAS 2026 `C(T+−T)/dt + G·T+ = P_t`, dt 미기재 (V); HotSpot SuperLU 빌드 (V, 소스) | 구간 평균 + 큰 스텝 감쇠 | 구간이 거칠면 더 뭉개짐 |
| **촘촘한 트레이스** | HotGauge IISWC'21: 200 µs (V); VOXEL 공개 코드: 이벤트를 ≥10 µs bin에 넣고 3D-ICE 과도 (코드 직접 확인) | 버스트보다 짧은 구간 | 버스트를 해상함 |
| **럼프드 RC** | Computational sprinting HPCA'12 (P); HeatCache 2026 (P) | 버스트 | 한 노드라 다이 수준 빠른 시정수를 못 봄 |
| **패키징 표준 (펄스 부하)** | Zth 중첩: Schweitzer TCAPT'09, Nexperia AN11261 (P); 다열원 Zth 행렬 JESD51-34 (S); Icepak LTI ROM, Flotherm BCI-ROM (P); MatEx DATE'15 (V); 데이터시트 근사 onsemi AND8220, Motorola AN569 (P) | 버스트 | 선형 스택이면 우리 답과 **같은 계산** |

패키지 쪽 대표인 imec IEDM'25(Chen et al.)도 원문에서 "Ansys Icepak steady-state"와 0.5 mm 정적 전력 맵(GPU 414 W, HBM 스택당 40 W)을 쓴다 (P\*). 정적 맵이 최대인지 평균인지는 적지 않았다.

측정 쪽도 같은 결론이다. LLM 전력 측정 연구는 NVML/DCGM 25~100 ms 간격이라 decode가 평평하게 보인다 (Patel ASPLOS'24 100 ms, P). NVML 센서는 100 ms 중 25 ms만 샘플한다 (Yang SC'24, P). 가장 촘촘한 부품별 측정도 1 ms다 (AMD FinGraV, P). **217 µs 버스트를 본 LLM 전력·열 연구는 찾지 못했다.**

## 3. 다시 돌린 결과 — 같은 스택, 입력만 다르게

같은 검증 솔버(MAPDL·Icepak으로 검증한 1D 층상 모델)에 각 관행의 전력 입력을 그대로 넣었다. 기준값은 **시간 스텝 없는 정확해**(모드 분해, MatEx와 같은 계산)이고, 시간 스텝 풀이와 0.5 µs에서 0.01% 일치한다. 트레이스 행은 구간과 버스트가 어긋나는 위치 8가지 중 최악(가장 높은 피크)을 쓴다. 긴 실행은 모든 위치를 만나기 때문이다.

| 관행 (대표) | V-Cache 실측 치수, F2B 6 µm | 지금 초록 (BEOL 티어) |
|---|---:|---:|
| 정적 최대 맵 (Stratum Eq.1 등) | 5.0 TB/s (**5.2배 비관**) | 5.0 (3.8배 비관) |
| 정적 평균 맵 (Tasa, DeepStack) | 104.2 (**4.0배 낙관**) | 104.2 (5.5배 낙관) |
| 10 ms 트레이스 (HotSpot 기본, MFIT) | 87.6 (3.4배 낙관) | 84.3 (4.5배) |
| 1 ms 에폭 (CoMeT, DRAMsim3) | 54.6 (**2.1배 낙관**) | 51.1 (2.7배) |
| 1 ms 음해법 한 스텝 (ATLAS 식) | 59.6 (2.3배 낙관) | 53.4 (2.8배) |
| 0.2 s / 333 ms 구간 (3D-ICE·PACT 예제) | 102.5 (4.0배 낙관) | 102.5 (5.4배) |
| 200 µs (HotGauge) | 26.2 (1.01배) | 18.9 (1.00배) |
| ~10 µs bin (VOXEL 코드) | 26.2 (1.01배) | 18.9 (1.00배) |
| 단일 노드 럼프드 | 84.0 (3.3배 낙관) | 77.3 (4.1배) |
| 데이터시트 Zth 근사 (two-pulse / AND8220 eq.22) | 25.4 / 24.6 (0.98 / 0.95배) | 18.5 / 18.3 |
| 단발 펄스 Zth, 이력 없음 (Infineon 계산법) | 30.7 (1.19배 낙관) | 21.1 |
| 정확한 Zth 중첩 = LTI ROM = MatEx | 25.8 | 18.9 |
| **버스트 해상 층상 과도 (우리)** | **25.8** | **18.9** |

읽는 법:
1. **관행은 양방향으로 틀린다.** 최대로 넣으면 5배 비관, 평균으로 넣으면 4배 낙관이다. 도구가 아니라 입력 탓이다.
2. **경계는 구간 길이 ≈ 버스트 길이다.** 200 µs 이하 구간이면 1.2% 이내, 500 µs면 1.5~1.8배, 1 ms면 2.1~2.7배, 10 ms면 3.4~4.5배 낙관이다 (V-Cache~BEOL). SOTA 논문들의 실제 설정(1~10 ms)은 전부 틀리는 쪽에 있다.
3. **패키징 표준 방법은 우리 답을 재현한다.** 버스트를 넣은 Zth 중첩과 LTI ROM은 우리와 같은 선형 시스템이라 같은 답이 나온다. 데이터시트 근사는 2~5% 보수적이다.
4. **정적 방법은 SRAM 다이 두께를 못 본다.** 1D에서 정적 최대·평균은 두께와 무관하게 5.0 / 104.2다. 버스트를 넣으면 10 µm 20.9 → 20 µm 26.7 → 50 µm 41.2 → 100 µm 54.2 TB/s (F2F)로 2.6배 움직인다. 실제 제품 치수(6 µm, 2차 자료)는 얇은 쪽 끝에 있다.

**정정.** 지난 세션 표의 V-Cache 26.0 TB/s는 차가운 상태에서 12주기만 돌린 시간 스텝 값이었다. 패키지 모드(~16 ms)가 덜 풀려 peak fraction이 0.2~0.7% 낮게 읽혔고, 정확해는 **25.8**이다 (BEOL 18.9는 그대로). 평균 전력 정상상태에서 출발해도 같은 이유로 4주기 후 +1% 높게 읽힌다. 이제 비교값은 전부 정확해 또는 주기 정상상태 출발로 계산한다.

## 4. HotSpot 7.0 자체로 다시 돌린 결과

3절은 우리 솔버에 각 관행의 입력을 넣은 것이다. "도구를 직접 돌리면 다르지 않냐"는 반론을 닫으려고, Stratum·Helios·Tasa·ATLAS가 쓰고 CoMeT이 감싸는 **HotSpot 7.0 자체**(github.com/uvahotspot/HotSpot, commit f18831e, 기본 빌드 SUPERLU=0)를 같은 V-Cache F2B 스택에 돌렸다 (`scripts/hotspot_rerun.py`). 패키지는 우리 경계조건(TIM 윗면 = 주변 온도, 보드 쪽 단열)과 같게 줄였다.

**두 가지 설정**
- **as-used**: 물리 층 하나당 lcf 층 하나. HotSpot에 내장된 열용량 계수 `C_FACTOR = 0.333`("lumping 때문에 floworks에 맞춘 피팅 계수", `temperature.h`)을 그대로 둠. 논문들이 도구를 쓰는 방식이다.
- **resolved**: 층을 2~10 µm 하위층으로 쪼개고 비열을 0.333으로 나눠 물리 열용량을 되돌림.

**결과** (peak fraction, 괄호는 TB/s)

| HotSpot에 넣은 입력 | 우리 (정확해) | HotSpot resolved | HotSpot as-used |
|---|---:|---:|---:|
| 정상상태, 버스트 전력 = 정적 최대 (Stratum·Helios 방식) | 1 (5.0) | 1 (5.0) | 1 (5.0) |
| 정상상태, 트레이스 = 평균 (Tasa 방식) | 0.0480 (104.2) | 0.0480 (104.2) | 0.0480 (104.2) |
| 7 µs 행 (버스트 해상) | 0.1935 (25.8) | 0.1886 (26.5) | 0.2236 (22.4) |
| 200 µs 행 (HotGauge) | 0.1912 (26.2) | — | 0.2237 (22.4) |
| 1 ms 행 (CoMeT) | 0.0915 (54.6) | 0.0905 (55.2) | 0.0887 (56.4) |
| 10 ms 행 (HotSpot 기본 설정) | 0.0571 (87.6) | — | 0.0605 (82.7) |

정상상태 열저항: HotSpot 0.02595 K/W, 우리 0.02595 K/W. HotSpot 과도 행은 각 실행의 마지막 1/4 구간 최댓값이고, 같은 행으로 돌린 복제 망과의 차이는 최대 0.006%다. 우리 열의 트레이스 값은 구간 정렬 8가지 중 최악이라 한 번의 실행 값과 ±0.5% 다를 수 있다.

**읽는 법**
1. **HotSpot도 같은 답을 준다.** 정상상태 열저항은 0.02595 K/W로 우리와 같다. 정상상태 모드는 트레이스를 정확히 평균한다(0.0480 = 듀티). 이것이 Tasa가 쓴 "트레이스 → 정상상태"의 실제 동작이다. 1 ms 행은 55~56 TB/s(정답 25.8의 2.1~2.2배 낙관), 10 ms 행은 82.7 TB/s(3.2배 낙관)다. 우리 표와 같은 쪽으로, 거의 같은 크기만큼 틀린다.
2. **도구 자체의 차이는 입력 차이보다 작다.** HotSpot의 망(각 층의 열용량을 그 층의 먼 쪽 면에 몰아 두는 1차 근사, `temperature_grid.c`)을 파이썬으로 그대로 복제했다. 같은 행으로 돌리면 도구 결과 6개와 0.006% 이내로 같다. 이 복제 망의 하위층을 2, 4, 8, 16배로 쪼개면 버스트 정확해가 0.1892 → 0.1913 → 0.1924 → 0.1930 → 0.1932로 우리 답 0.1935에 1차 수렴한다. **물리는 같고, 차이는 이산화뿐이다** (`assets/sweep/hotspot_replica.json`).
3. **내장 열용량 계수는 따로 14% 비관을 더한다.** 도구를 쓰는 그대로(as-used) 버스트를 넣으면 22.2~22.4 TB/s로 정답 25.8보다 14% 낮다. 열용량의 2/3를 빼 버리는 계수라 짧은 버스트의 완충이 줄어든다. 도구 설정에서 오는 오차는 행에 따라 3~16%이고, 입력 관행에서 오는 오차는 2~5배다. 다만 "HotSpot 과도로 확인했다"는 논문의 버스트 결과에는 이 14% 편향이 들어 있다.

## 5. 우리 기여를 어떻게 말해야 하나 — 신규성 충돌

**말하면 안 되는 것**
- **"새 열해석 방법"**: 층상 과도, Zth 중첩, LTI ROM은 표준이다. 우리 과도 해석은 JESD51-34 식 Zth 중첩이나 Icepak LTI ROM과 같은 계산이다.
- **"적층 메모리 LLM 가속기에서 처음 한 과도 열해석"**: ATLAS(2026)가 HotSpot-7 과도를 쓴다 (dt 미기재). VOXEL(MICRO'26)의 **공개 코드**는 SRAM·DRAM 이벤트 에너지를 ≥10 µs bin에 넣고 3D-ICE 과도를 돌린다 (방법론상 우리 방식과 같음). 다만 VOXEL 논문의 DSE는 0.7 W/mm² 순간 밀도 상한을 쓰고, 버스트 길이·듀티를 설계량으로 다루지 않으며, 정상상태와 과도를 비교하지 않는다.
- **"얇은 다이는 짧은 펄스에 불리하다"는 물리 자체**: Araga JJAP'18(25 vs 725 µm, 펄스 가열 측정), Damcevska Sci. Rep.'23(박화가 C_th를 3.2배 줄여 서지에 불리), Oprins imec'11·'12(적층 다이 시정수 100~200 µs 실측)가 이미 보였다.

**말할 수 있는 것**
1. decode 스텝에서 적층 SRAM 부하의 **시간 구조(버스트 217 µs, 듀티 4.80%)를 유도**한 것. 찾은 문헌 중에 이것을 하는 LLM 전력·열 연구는 없다.
2. **지금 쓰이는 판정 관행이 같은 설계를 양방향으로 4~5배 틀리게 판정한다**는 정량화. 대표 관행마다 원문으로 확인한 입력 방식을 우리 스택에 재현했고, HotSpot 7.0 자체로도 확인했다.
3. **얇게 간 SRAM 다이가 버스트 완충을 잃는다**는 설계 결과. 물리는 알려져 있고, 이것을 하이브리드 본딩 SRAM-under-logic과 LLM decode 부하에 대역폭 예산으로 적용한 것이 새롭다.

**아직 주장하면 안 되는 것**: "정상상태 박화 연구(imec IEDM'25 등)는 박화를 권하는데 우리는 반대"라는 대비. 조사 에이전트의 추론일 뿐 돌려 보지 않았다. imec IEDM'25에서 얇게 가는 것은 SRAM 다이가 아니라 HBM 맨 위 DRAM 다이(169 → 41 µm)이고, 효과도 0.4 °C라 스스로 "제한적"이라고 결론 낸다 (원문 확인).

## 6. 남은 확인

| 항목 | 왜 | 상태 |
|---|---|---|
| Sharda & Yu, JETCAS 2025 "STCO for LLM accelerators with advanced packaging" | 가장 가까운 선행일 수 있었음 | **확인, 충돌 아님.** Ansys Mechanical 정적 전력밀도 + 200 W 상한. 3D SRAM 구성은 PPA만 보고, 열 결과는 HBM-on-logic(65 W)·SLT(>200 W) |
| imec IEDM 2025 (Chen et al., 17-3) | 리뷰어가 기준으로 들 가능성이 가장 큰 memory-on-GPU 열 연구 | **확인.** Icepak 정상상태, 정적 0.5 mm 전력 맵 |
| Sharda et al., JXCDC 2025 (Georgia Tech / SK hynix) | HBM-on-logic LLM 열 | **확인.** 평균 전력 가정을 문장으로 적음(III-A). 로직은 정적 최대 예산 |
| ATLAS의 dt | 촘촘하면 가장 가까운 선행 | 논문에 없음. 코드 공개 대기 |
| Pei et al. 2026, Case Stud. Therm. Eng. "spatiotemporal thermal … 3D chiplet" | 제목상 시공간 과도 | ScienceDirect가 자동화 브라우저를 차단. 직접 열어야 함 (오픈 액세스) |
| 9800X3D SRAM 다이 6 µm | 표의 "실측 치수" 근거 | 여전히 분해 분석 기사 (S). AMD ISSCC'22 V-Cache는 발표 전용이라 논문이 없고, MI300 ISSCC'24는 F2B·9 µm 피치·IOD 안 256 MB 캐시는 적지만 두께는 없음. 초록에는 "보도된 값" + 6~100 µm 범위로 |
| 재검증 못 한 99건 | 인용 전 원문 확인 | 인용할 것만 골라 확인 필요 |

## 7. 인용 목록 (등급)

**LLM·적층 메모리 아키텍처**
- Y. Pan et al., "Stratum: System-Hardware Co-Design with Tiered Monolithic 3D-Stackable DRAM for Efficient MoE Serving," MICRO 2025, doi:10.1145/3725843.3756043 — V
- C. Li et al., "Hardware-Software Co-design for 3D-DRAM-based LLM Serving Accelerator" (Helios), arXiv:2603.04797, 2026 — V
- C. Ai et al., "Rethinking Compute Substrates for 3D-Stacked Near-Memory LLM Decoding," arXiv:2604.04253, 2026 — V
- J. Sharda, S. Yu, "System-Technology Co-Optimization Methodology for LLM Accelerators With Advanced Packaging," IEEE JETCAS 15(4):577-584, 2025, doi:10.1109/JETCAS.2025.3596593 — P\*
- J. Sharda, M. Manley, J. Kwak, C. Park, M. Bakir, S. Yu, "3-D Stacked HBM and Compute Accelerators for LLM: Optimizing Thermal Management and Power Delivery Efficiency," IEEE JXCDC 11:116-122, 2025, doi:10.1109/JXCDC.2025.3617298 — P\* (평균 전력 가정, III-A)
- W.-H. Huang et al., "A3D-MoE," arXiv:2507.19142, 2025 — V (주의: 별도 SRAM 티어 없음, V-Cache SRAM은 HBM 베이스 다이 위)
- S. He et al., "Tasa: Thermal-aware 3D-Stacked Architecture Design with Bandwidth Sharing for LLM Inference," arXiv:2508.07252, 2025 — V (학회는 재검증에서 확인 안 됨)
- Z. Mo et al., "DeepStack," arXiv:2604.04750, v4 "MICRO version" — V
- C. Li et al., "A Full-Stack Performance Evaluation Infrastructure for 3D-DRAM-based LLM Accelerators" (ATLAS), arXiv:2604.08044, 2026 — V
- Y. Liu et al., "Exploring the Efficiency of 3D-Stacked AI Chip Architecture for LLM Inference with VOXEL," arXiv:2604.26821, 2026; 코드 github.com/yiqiliu2/voxelsim — P, 코드 직접 확인 (`TraceConfig`: 250 ms에 최대 25,000 bin, 3D-ICE `transient step dt, slot dt`)
- C. Duan et al., "HPIM," arXiv:2509.12993 — V (주의: 2.5D, memory-on-logic 아님)

**패키지·스택 열**
- R. Mathur et al., "Thermal Analysis of a 3D Stacked High-Performance Commercial Microprocessor using Face-to-Face Wafer Bonding Technology," ECTC 2020, arXiv:2007.16179 — V (과도 입력 파형은 논문에 없음, 상수 maxpower는 추정)
- Y. Chen et al. (imec), "Beyond HBM-on-GPU: Thermal Design Envelope for 3D Volumetric DRAM-on-GPU Integration," ESSERC 2026, arXiv:2609.24343 — V
- Y. Chen et al. (imec), "Breaking Thermal Bottleneck in 3D HBM-on-GPU Integration via System-Technology Co-Optimization," IEDM 2025, doi:10.1109/IEDM50572.2025.11353711 — P\* (Icepak 정상상태)
- A. Smith et al. (AMD), "AMD Instinct MI300 Series Modular Chiplet Package – HPC and AI Accelerator for Exa-Class Systems," ISSCC 2024, paper 11.1, doi:10.1109/ISSCC49657.2024.10454441 — P\* (F2B 하이브리드 본딩, 9 µm 피치, IOD 안 256 MB Infinity Cache)
- H. Oprins et al., SEMI-THERM 2011 / Electronics Cooling 2012 (적층 다이 과도 시정수 100~200 µs) — P

**열 시뮬레이터**
- HotSpot 7.0, github.com/uvahotspot/HotSpot (commit f18831e); J.-H. Han et al., ITherm 2022 — V (소스: `template.config` 10 ms, 정상상태 = 트레이스 평균, `C_FACTOR` 0.333)
- K. Zhu et al., "3D-ICE 4.0," DATE 2026, arXiv:2512.05823 — V
- Z. Yuan et al., "PACT," IEEE TCAD 41(4), 2022 — V
- L. Pfromm et al., "MFIT," ACM TODAES 2025 — V
- L. Siddhu et al., "CoMeT," ACM TACO 19(3), 2022 — V
- S. Li et al., "DRAMsim3," IEEE CAL 19(2), 2020 — V
- A. Hankin et al., "HotGauge," IISWC 2021 — V
- S. Pagani et al., "MatEx," DATE 2015 — V

**펄스 부하 방법**
- onsemi AND8220; Nexperia AN11261; Infineon MOSFET 동적 열 노트; ROHM 64AN028E; TI SLUAAT8 — P
- D. Schweitzer, IEEE TCAPT 32(2), 2009 (arXiv:0709.1852) — P; JEDEC JESD51-34, JESD51-14 — S
- Ansys Icepak LTI ROM 가이드 2025 R1; Siemens Flotherm BCI-ROM — P

**관행 식의 계보**
- M. O'Connor et al., "Fine-Grained DRAM," MICRO 2017 — P
- S. W. Keckler et al., "GPUs and the Future of Parallel Computing," IEEE Micro 31(5), 2011 — P
- Y. Eckert, N. Jayasena, G. H. Loh, "Thermal Feasibility of Die-Stacked Processing in Memory," WoNDP 2014 — P

**LLM 전력 측정**
- P. Patel et al., ASPLOS 2024 — P; Z. Yang et al., SC 2024 — P; V. Singhania et al. (AMD), "FinGraV," arXiv:2412.12426 — P

**다이 박화·열용량**
- Y. Araga et al., JJAP 57(4S) 04FC06, 2018 — P
- J. Damcevska et al., Sci. Rep. 13, 2023 — P
- A. Raghavan et al., "Computational Sprinting," HPCA 2012 — P

## 8. 3절 숫자가 기대는 두 가정 — 버스트 모양과 패키지 경계 (2026-09-27 저녁, Claude)

3·4절의 모든 행은 두 가정을 공유한다. **(가) 티어 부하는 스텝마다 216.7 µs 한 덩어리**이고, **(나) TIM 윗면 온도가 고정된 이상적 뚜껑** 경계다. 둘 다 버스트가 가장 크게 보이는 쪽이라 25.8 TB/s와 "정적 평균 4.0배 낙관"은 상한 코너다. 두 가정을 하나씩 풀고, 3D 매크로 모델(MAPDL)로 다시 확인했다. 바이트·스텝당 에너지(8.235 mJ/다이)·주기 4.515 ms는 그대로라서, 정적 평균(104.2 TB/s)과 정적 최대(5.0 TB/s)의 답은 변하지 않고 정확해만 움직인다.

### 8-1. 버스트 모양 — 티어가 어떤 가중치를 드나 (`scripts/burst_shape.py`)

티어는 가중치만 받는다(Gate 6). Gate-1 재생의 LIP는 새 줄을 LRU 끝에 넣으므로 **먼저 들어온 바이트, 즉 0~9층 가중치**를 남긴다. 그 층의 행렬 넷(QKV·O·gate_up·down)은 B_R 19 TB/s로 읽히고, 사이에 HBM 어텐션(층당 67 MB, 10.5 µs)과 커널 간격이 낀다. 스텝의 고정 시간 t0 1.852 ms는 셋으로 나눴다: 전부 호스트 간격 / 커널당 1.5 µs + 나머지 호스트 간격(기본, 가정값) / 커널에 고르게. 각 스케줄은 모드 분해 정확해로 풀었고, 0.25 µs 후방 오일러와 −0.06%(V-Cache)·−0.11%(BEOL)로 맞는다.

| 티어가 드는 가중치 (V-Cache F2B 6 µm, 이상적 뚜껑) | 정확해 TB/s | 정적 평균 낙관 | 정적 최대 비관 | 1 ms 에폭 낙관 |
|---|---:|---:|---:|---:|
| 한 덩어리 (3절 가정) | 25.8 | 4.03배 | 5.2배 | 2.11배 |
| **0~9층 (Gate-1 LIP), 1.5 µs/커널** | **34.5** | **3.02배** | 6.9배 | 1.58배 |
| 0~9층, t0 전부 호스트 / 커널에 분산 | 29.7 / 48.3 | 3.51 / 2.16배 | 5.9 / 9.7배 | 1.84 / 1.14배 |
| lm_head + 마지막 층 (가장 조밀한 연속 배치) | 29.3 | 3.55배 | 5.9배 | 1.86배 |
| 9.4층을 32층에 고르게 | 58.3 | 1.79배 | 11.7배 | 1.32배 |
| 층마다 down proj. (+O) | 72.5 | 1.44배 | 14.5배 | 1.17배 |
| 모든 행렬의 페이지 슬라이스 (HBM과 동시, 2.4 TB/s) | 77.2 | 1.35배 | 15.4배 | 1.06배 |

1. **한 덩어리는 최악이다.** 재생이 실제로 두는 배치(0~9층)에서도 버스트가 0.46 ms에 퍼져 피크가 25% 낮다.
2. **방향은 모든 배치에서 유지된다.** 정적 최대는 5~15배 비관, 정적 평균은 1.35~4배 낙관이다.
3. **배치가 열 설계 변수다.** 같은 바이트를 층에 퍼뜨리면 피크가 2.2배 내려간다(34.5 → 72.5 TB/s). 정적 맵은 이 차이를 보지 못한다.
4. 200 µs 트레이스(HotGauge)는 퍼진 배치에서 더 이상 정확하지 않다(층당 6 µs 펄스가 행보다 짧아 최대 1.31배 낙관).

### 8-2. 패키지 경계 — TIM 위에 무엇이 있나 (`scripts/package_boundary.py`)

생산 MAPDL 덱(`mapdl_vcache.py` prod)은 로직 접합 100 °C로 보정한 막 계수를 쓴다. TIM 위 외부 저항 R_ext = 0.149 K/W/다이로, 다이 스택 R 0.026의 5.8배다. 외부 경로는 느려서(R_ext × 다이 열용량 ≈ 0.15 s ≫ 4.5 ms) 평균 전력만 보고, 버스트는 다이 스택만 본다: pf = (R_ext·D + pf_stack·R_stack)/(R_ext + R_stack). 막을 망에 넣어 정확해로 풀었다(R_ext = 0에서 3절과 일치). 뚜껑(Cu 2 mm)·TIM2(100 µm)·냉각판(Cu 3 mm)의 열용량을 넣고 같은 R_ext를 맞춰도 결과가 넷째 자리까지 같다. 정하는 것은 **R_ext/R_stack 하나**다.

| R_ext/R_stack | 한 덩어리 | 0~9층 (Gate-1) | 정적 평균 낙관 (한 덩어리 / Gate-1) | 정적 최대 비관 | 1 ms 에폭 낙관 | 10 ms 트레이스 낙관 |
|---:|---:|---:|---:|---:|---:|---:|
| 0 (이상적 뚜껑, 3절) | 25.8 | 34.5 | 4.03 / 3.02배 | 5.2 / 6.9배 | 2.11 / 1.58배 | 3.39 / 2.54배 |
| 1.9 | 51.2 | 61.7 | 2.04 / 1.69배 | 10 / 12배 | | |
| 2.9 | 58.6 | 68.6 | 1.78 / 1.52배 | 12 / 14배 | 1.44 / 1.23배 | 1.70 / 1.45배 |
| 5.8 (생산 덱) | 71.9 | 80.2 | 1.45 / 1.30배 | 14 / 16배 | 1.27 / 1.14배 | 1.41 / 1.27배 |

B200급 수랭 패키지(접합-냉각수 0.04~0.085 K/W)면 R_ext/R_stack은 2.3~5.7이다. 이 모델의 보정값(0.085 K/W, 700 W에서 60 K)은 그 범위의 보수적 끝이다. 박화 효과도 줄어든다: SRAM 다이 10 → 100 µm가 이상적 뚜껑에서 2.6배(20.9 → 54.2 TB/s), 생산 덱 경계에서 1.4배(64.6 → 91.3)다.

### 8-3. 3D 매크로 모델로 확인 (`scripts/mapdl_vcache_schedules.py`, ampere MAPDL 2026 R1)

같은 C2 매크로 단위셀(153 × 518 µm, L자 주변회로 28.5%)에 V-Cache F2B 스택을 넣었다. 정적 맵은 정상상태 세 번(로직만 / + 평균 전력 / + 버스트 전력 유지), 과도는 스케줄을 커널 단위로 load step에 넣고 평균 전력 정상상태에서 6주기다. **검증:** 이상적 뚜껑·균일에서 Gate-1 스케줄의 3D 피크가 같은 스텝으로 푼 1D와 −0.13%(0.142788 대 0.142977 K)다. 생산 덱 균일 한 덩어리는 1D 막 해와 +0.2%다.

| 읽기 전력 중 주변회로 몫 | 이상적 뚜껑, 한 덩어리 | 이상적 뚜껑, Gate-1 (S1) | 생산 덱, 한 덩어리 | 생산 덱, Gate-1 (S1) |
|---|---:|---:|---:|---:|
| 균일 (면적 몫 28.5%) | 25.7 (pf 0.194) | 34.5 (0.145) | 71.5 (0.070) | 80.2 (0.062) |
| 50% | **19.1** (0.262) | 26.9 (0.186) | 59.9 (0.084) | 70.7 (0.071) |
| 70% | **16.0** (0.313) | 23.1 (0.217) | 52.3 (0.096) | 63.9 (0.078) |
| 90% | **14.1** (0.354) | 20.7 (0.242) | 46.6 (0.107) | 58.5 (0.086) |

한 덩어리 행은 모두 스케줄 덱(버스트당 서브스텝 109개)으로 다시 풀어 같은 스텝으로 맞췄다(`mapdl_vcache_schedules.py --phi-table` → `assets/mapdl/vcache_sched/phi_sweep.json`, 16건 오류 0). 생산 덱·90%에서 층마다 down(S3)은 88.4 TB/s(pf 0.057)다. 이상적 뚜껑 한 덩어리는 **주변회로 몫이 약 50%를 넘으면 19 TB/s 아래**다. Gate-1 배치는 이상적 뚜껑이어도 90%까지 모두 19 이상이다.

정적 평균은 모든 행에서 104.2, 정적 최대는 5.0 TB/s다. 주변회로 집중은 정상상태 피크를 1.06배(생산 덱)~1.38배(이상적 뚜껑)만 올리지만, 짧은 버스트의 국소 상승은 2.5배 올린다(이상적 뚜껑 한 덩어리 0.481 대 균일 0.191 K, 밀도 비 3.16배에 가깝다). 버스트 동안 열이 옆으로 퍼질 시간이 없기 때문이다. 그래서 집중될수록 pf가 커진다.

**가장 나쁜 코너**(이상적 뚜껑 + 주변회로 90% + 한 덩어리)에서는 14.1 TB/s로 **패브릭 한계 19에 못 미친다**. 이 코너에서는 정적 평균이 **7.4배 낙관**, 정적 최대가 2.8배 비관이다. 같은 코너라도 Gate-1 배치면 20.7로 간신히 통과하고, 현실 패키지 경계에서는 모든 배치가 47~88 TB/s로 여유 있게 통과한다. 3D 결과에 외부 막을 식 pf = (R_ext·D + pf_lid·R_lid)/(R_ext + R_lid)로 얹으면(R_lid는 같은 전력 분포의 정상상태 상승/전력, 생산 덱 90% 3D를 0.6% 안에서 재현) 90%·한 덩어리가 19 TB/s 아래로 가려면 **R_ext < 0.015 K/W/다이**여야 한다. B200급 수랭(0.06~0.15)보다 한 자릿수 작다. 즉 **열이 패브릭보다 먼저 막으려면 이상적 냉각, 주변회로 집중 50% 이상, 연속 배치가 모두 겹쳐야 한다.**

### 8-4. 초록에 주는 의미

- **유지:** 관행 스크리닝 식(정적 최대)은 모든 경우에 판정을 뒤집는다. 비관 폭은 2.8~18배다. 현실 패키지에서는 3절(5.2배)보다 더 크게 틀린다.
- **바뀜:** "정적 평균도 4배 낙관이라 두 관행이 대칭으로 틀린다"는 한 코너의 숫자다. 정적 평균의 낙관은 **1.2~7.4배**이고, 패키지(R_ext/R_stack), 매크로 안 전력 집중, 배치가 정한다. 셋 다 정적 맵이 볼 수 없는 양이다. 그래서 초록의 논리는 "두 관행이 각각 몇 배 틀린다"보다 **"틀리는 폭이 설계마다 1.2~18배로 달라져 정적 판정으로는 알 수 없다. 버스트를 넣은 해석(모드 분해·Zth 중첩, 계산 비용은 초 단위)이 필요하다"**로 쓰는 편이 튼튼하다.
- **새로 말할 수 있는 것 (ECTC 청중용):** 버스트 민감도는 다이 스택이 전체 열저항에서 차지하는 비율이 정한다. 냉각이 좋아질수록(R_ext↓, 직접 액체 냉각) 정적 평균이 더 틀린다. 워크로드 쪽 배치(어떤 가중치를 티어에 두나)는 같은 바이트로 피크를 2배 넘게 바꾸는 열 설계 변수다.
- **"열이 걸림돌이 아니다"는 조건부로 써야 한다.** 현실 패키지에서는 참이다. 이상적 냉각 + 강한 주변회로 집중 + 연속 배치 코너에서는 열이 패브릭보다 먼저 막는다.

### 8-5. 남은 확인

| 항목 | 상태 |
|---|---|
| 커널 간격 1.5 µs와 호스트 간격 분할(가정값) | **측정함 (17:22).** RTX PRO 5000에서 Llama-3.1-8B B=8 문맥 2048 decode를 nsys로 캡처했다(`scripts/gpu/decode_timeline.{py,sh}`, 분석 `decode_timeline_analyze.py`, `assets/sweep/decode_timeline/`). CUDA 그래프 한 스텝은 19.57 ms, 커널 1,515개다. 가중치 GEMM 225개가 71%, 어텐션 bmm 64개가 15%, 작은 커널 1,226개(norm·rotary·복사 등, 중앙값 1.5 µs)가 11%, **커널 사이 실행 간격은 중앙값 0.42 µs**로 3%다(eager는 1.47 µs). 즉 가정한 "커널당 1.5 µs"는 실행 간격(0.4 µs)에 작은 커널 시간을 더한 값에 해당하고, vLLM처럼 층당 커널 ~10개로 융합한 경로와 맞는다. 측정한 커널 순서를 그대로 쓰고 가중치·어텐션만 B200 속도로 다시 잰 S1(`burst_shape.schedule_measured`)은 **이상적 뚜껑 46.1, R_ext/R_stack 2.9에서 78.7, 생산 덱 87.8 TB/s**다. 범위의 "커널에 분산" 끝(48.3)에 가깝다. HF 모듈은 층당 작은 커널이 ~35개라 더 퍼지기 때문이다. 기본값(34.5)은 측정 구조보다 보수적이다. 호스트 간격(B200 vLLM의 스케줄러·샘플링)은 이 장비로 잴 수 없다 |
| AEDT Icepak 독립 확인 | **확인함 (17:14).** 연구실 PC(DSIL_remote_2)의 V-Cache F2B 기둥(10 × 10 µm, 사면체 70,862개, 이상적 뚜껑, 차가운 출발, 한 덩어리, dt 3.612 µs). 15:50 실행은 필드 저장이 꺼진 채 6.61 ms에서 엔진 오류로 멈춰 모니터가 두 점뿐이었다. 원본은 두고 복사본 `IcepakFEADesign2`(10스텝마다 저장, 2주기)를 다시 풀었다. 결과 파일 복사 오류 때문에 1.95 ms 이후는 NaN이지만, 버스트와 1.7 ms의 냉각 구간 53개 샘플은 남았다. **같은 dt로 푼 우리 1D와 최대 0.006 K(상승 15.4 K의 0.04%) 차이**이고, 마지막 버스트 중 샘플은 34.9202 대 34.9202 °C다. 둘 다 정확해보다 0.44% 낮은데, 이는 3.6 µs 시간 스텝 오차다. 기록은 `assets/aedt/vcache_icepak_design2.json`, 추출 스크립트는 `scripts/aedt/vcpeaks.py`·`vcsamples.py` |
| 주변회로 집중 90%의 근거 | 소자팀 값이 아니라 스윕 끝값이다. 3D 스윕(50·70%)을 돌렸다. 이상적 뚜껑·한 덩어리에서는 **주변회로 몫이 약 50%를 넘으면 19 TB/s 아래**로 떨어진다(균일 25.7 → 50% 19.1 → 70% 16.0 → 90% 14.1). 생산 덱 경계에서는 71.5 → 59.9 → 52.3 → 46.6으로 모두 통과한다. 소자팀에 물을 것은 읽기 전력 중 주변회로 몫이다 |
