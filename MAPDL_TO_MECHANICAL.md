# MAPDL 모델을 Ansys Mechanical(Workbench)에서 열기

발표 자료에 Mechanical 전체 화면(트리 · 상세 창 · 3D 뷰 · 시간 그래프 · 표)을 넣기 위한 절차.
서버(dsil-sy)에는 Mechanical이 없고 MAPDL 솔버만 있으므로, **Workbench가 깔린 연구실 Windows PC**에서 한다.

해석 자체는 서버의 MAPDL로 이미 끝났다(`scripts/mapdl_macro.py`, 결과는 `ECTC_STORY.md` 5-M).
여기서 하는 것은 **같은 모델을 Mechanical에서 다시 풀어 화면을 얻는 것**이다. 결과가 서버 값과 맞는지로
설정이 제대로 됐는지 확인할 수 있다(아래 "맞춰볼 값").

## 가져갈 파일

`assets/mapdl/macro/macro_c2_for_mechanical.cdb` — C2 매크로 하나(153 × 518 µm), 요소 25,200개(SOLID70),
재료 5종(실제 밀도·비열), 이름 붙은 선택 5개가 들어 있다. 하중은 들어 있지 않다.

| Named Selection | 무엇 |
|---|---|
| `TIER` | SRAM 티어 두 층 전체 |
| `TIER_ARR` | 티어 중 어레이 영역 (133 × 426 µm) |
| `TIER_PER` | 티어 중 주변회로 L자 영역 (면적 28.5%) |
| `LOGIC` | 로직 소자층 (1 µm) |
| `SINK` | 방열면 (z = 0, TIM 바깥면) 노드 |

## 1. 프로젝트 만들기

1. Workbench 2026 R1 실행
2. Toolbox → Component Systems → **External Model**을 Project Schematic에 끌어다 놓기
3. External Model의 **Setup** 더블클릭 → 파일 추가에서 `.cdb` 선택
4. Unit System: **Metric (m, kg, N, s, V, A)** — 모델이 미터 단위다. 다르게 두면 치수가 10⁶배 틀어진다
5. 상단 **Update Project**
6. Toolbox → Analysis Systems → **Steady-State Thermal**을 External Model의 **Setup** 칸 위에 끌어다 놓아 연결
7. 같은 방법으로 **Transient Thermal**을 끌어다 놓되, Steady-State Thermal의 **Solution** 칸 위에 놓는다
   (정상상태 해가 과도 해석의 초기 온도가 된다)

## 2. 재료 확인

Model 트리의 각 바디에 재료가 붙었는지 확인한다. 안 붙었으면 Engineering Data에 아래 값으로 만들어 바디별로 지정한다.

| 층 | 열전도도 [W/m·K] | 밀도 [kg/m³] | 비열 [J/kg·K] |
|---|---|---:|---:|
| TIM | 5.0 | 2500 | 800 |
| Si, logic | 110 | 2330 | 700 |
| BEOL | 2.5 (등방) — 이방성 케이스는 x·y 25, z 2.5 | 2300 | 900 |
| SRAM_tier (a-IGZO) | 1.6 | 6100 | 340 |

## 3. 정상상태 하중 (Steady-State Thermal) — 평균 전력

| 하중 | 적용 대상 | 값 |
|---|---|---|
| Convection | `SINK` (면) | 필름 계수 **8187.4 W/m²·K**, 주변 온도 **40 °C** |
| Internal Heat Generation | `LOGIC` | **4.3669e11 W/m³** |
| Internal Heat Generation | `TIER_ARR` | **3.1893e9 W/m³** |
| Internal Heat Generation | `TIER_PER` | **7.1973e10 W/m³** |

티어 값은 주변회로 전력 비율 φ = 0.9, 듀티 평균이다. 균일 케이스(φ = 0.285)로 하려면 두 티어 영역 모두 2.2800e10 W/m³.

Solve → Solution에 Temperature 삽입. 이 해가 주기의 평균 상태다.

## 4. 과도 하중 (Transient Thermal) — 듀티 4.80%의 톱니 모양

Analysis Settings

- Step End Time: **0.013545 s** (3주기)
- Auto Time Stepping: On, Initial 5e-6 s, Minimum 1e-6 s, Maximum 2e-5 s

하중: Convection과 `LOGIC` 발열은 정상상태와 같은 값으로 둔다. 두 티어 영역의 발열은 Magnitude를
**Tabular**로 바꾸고 아래 표를 넣는다. 켜짐 = 켜진 값, 꺼짐 = 0. 1 µs 간격은 계단을 흉내 내는 것이다.

| 시간 [s] | 상태 |
|---|---|
| 0 | 켜짐 |
| 2.167e-4 | 켜짐 |
| 2.177e-4 | 꺼짐 |
| 4.515e-3 | 꺼짐 |
| 4.516e-3 | 켜짐 |
| 4.7317e-3 | 켜짐 |
| 4.7327e-3 | 꺼짐 |
| 9.030e-3 | 꺼짐 |
| 9.031e-3 | 켜짐 |
| 9.2467e-3 | 켜짐 |
| 9.2477e-3 | 꺼짐 |
| 1.3545e-2 | 꺼짐 |

켜진 값: `TIER_ARR` **6.6444e10 W/m³**, `TIER_PER` **1.4994e12 W/m³** (φ = 0.9).

Solution에 **Temperature**(스코프 `TIER`)와 **Temperature Probe**(최대값)를 넣으면 하단 Graph·Tabular Data
창에 톱니 모양 시간 이력이 나온다. 보내준 예시 슬라이드와 같은 화면 구성이다.

## 맞춰볼 값

서버 MAPDL 결과(`assets/mapdl/macro/results.txt`)와 비교한다. 과도 해석은 3주기라 서버의 6주기보다
조금 덜 수렴했을 수 있다. 차이가 1% 안팎이면 설정이 맞은 것이다.

- 정상상태, φ = 0.9: 티어 평균 온도는 약 100.01 °C (싱크측 약 93.6 °C)
- 과도, φ = 0.9: 버스트 끝 티어 피크는 `results.txt`의 `prod_k1_phi90` peak 값

## 주의

- 이 절차는 이 세션에서 실행해 보지 못했다(Mechanical이 없음). External Model이 SOLID70 메시를 읽는 것,
  CDB의 component가 Named Selection으로 들어오는 것은 Ansys 문서상 지원 사항이지만, 막히는 단계가 있으면
  그 화면을 캡처해서 알려줄 것.
- 결과 PNG를 Mechanical 창처럼 합성하지 않는다. 돌리지 않은 프로그램의 화면을 만드는 것이 되기 때문이다.
