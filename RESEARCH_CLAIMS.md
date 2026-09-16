# Ledger3D 연구 주장과 논문 분리안

2026-09-16 B200 보존 실험까지 반영한 동결본이다. 이 문서는 논문의 주장, 그 주장을 지지하는 증거, 아직 필요한 증거를 섞지 않기 위한 체크리스트다.

## 한 문장 결론

LLM의 weight, attention KV, recurrent state는 크기·수명·읽기/쓰기·공유 방식이 다르므로, 3D SRAM에는 특정 데이터 종류를 고정해서 넣는 대신 **입장 가능한 객체만 고른 뒤 한 스텝에서 줄이는 HBM 이동량을 상주 바이트와 비용으로 나눈 한계 이득**이 큰 객체를 배치해야 한다.

## 50-word novelty statement

> Ledger3D treats LLM inference memory as competing objects—weights, attention KV, and recurrent state—rather than a single cache. It admits objects only when protected coverage can reduce off-chip traffic, then allocates scarce stacked SRAM by traffic saved per resident byte. B200 cache-proxy experiments directly validate both the ranking and capacity-cliff counterexamples.

## 정책은 세 단계다

### 1. 원장을 만든다

각 객체 또는 페이지 `i`에 대해 다음 값을 스텝·층·phase마다 기록한다.

- 상주 바이트 `S_i`
- 배치하지 않았을 때의 HBM read/write 바이트 `R_i`, `W_i`
- 유효 수명, 다음 접근 시각, dirty/write-back 바이트
- 요청 간 공유도와 MoE route probability
- fast tier가 덮을 수 있는 비율 `coverage_i(C)`
- 이동·정책 전환·eviction·기존 캐시 손실 비용

### 2. 입장 여부를 먼저 판정한다

다음의 한계 이득이 양수이고 안전 여유보다 클 때만 객체를 fast tier 후보로 인정한다.

```text
gain_i(C) = avoided_HBM_bytes_i(C) / BW_HBM
          - served_tier_bytes_i(C) / BW_tier
          - migration_i - switching_i - writeback_i
          - eviction_opportunity_i - lost_overlap_i
```

`coverage`만으로 보편적인 임계값을 정하지 않는다. 이번 B200 L2 대리 실험에서는 state가 82.4% 덮일 때 세 layer granularity에서 모두 이득이었고, 61.8%에서는 granularity에 따라 결과가 갈렸으며, 30.9%에서는 모든 정책이 손해였다. 이 경계는 B200·이 커널의 교정점이지 3D SRAM의 보편 상수가 아니다.

추가 3D SRAM은 기존 L2를 빼앗지 않으므로 `eviction_opportunity`가 작다. B200 persisting-L2 실험은 기존 L2를 예약하므로 이 항이 크다. 두 결과를 같은 하드웨어 주장으로 합치지 않는다.

### 3. 입장한 후보끼리 용량을 나눈다

```text
maximize  Σ gain_i(x_i)
subject to Σ x_i ≤ C,  0 ≤ x_i ≤ S_i
```

실행기에서는 페이지 또는 layer slice의 `marginal gain / placed byte` 순으로 채우고, 작은 변동에 매 스텝 재배치하지 않도록 hysteresis와 최소 상주 시간을 둔다. 여러 요청이나 tenant가 경쟁하면 공정성 제한을 별도로 둔다.

## B200에서 직접 닫힌 부분

### 동일 객체 실험

64 MiB weight·KV·state를 같은 커널과 같은 접근 순서 집합에서 비교했다. state는 상주량당 논리 이동량이 2회(read+write), weight와 KV는 1회(read)였다.

| 결과 | weight | KV | state |
|---|---:|---:|---:|
| 두 B200 통합 기하평균 | 1.0554× | 1.0562× | **1.1099×** |
| 장치×순서×반복 셀 1위 | 0/36 | 0/36 | **36/36** |

이 결과는 `traffic saved / resident byte`가 동일 크기 객체의 배치 순위를 예측했다는 증거다.

### 크기·layer-slice sweep

18개 조건, 1,620 trial, validation 오류 0이다.

| 객체 크기 | persisting 예약 비율 | state가 default보다 빠른 셀 | state가 W/KV보다 빠른 셀 | 결론 |
|---:|---:|---:|---:|---|
| 16 MiB | 100% | 27/54 | 28/54 | 기본 캐시로 충분해 강제 배치 이득이 거의 없음 |
| 32 MiB | 100% | 54/54 | 48/54 | 입장, state 우선 |
| 64 MiB | 100% | 54/54 | 54/54 | 입장, state 우선 |
| 96 MiB | 82.4% | 53/54 | 53/54 | 입장 가능, state 우선 |
| 128 MiB | 61.8% | 36/54 | 41/54 | layer granularity 의존, 다시 계측 |
| 256 MiB | 30.9% | 0/54 | 19/54 | 강제 배치 거부 |

이는 “재사용이 많으면 무조건 올린다”를 반증한다. 이득이 큰 객체라도 충분히 보호하지 못하거나 다른 캐시 데이터를 밀어내면 손해가 난다.

## 모델별 첫 정책

다음은 고정 라벨이 아니라 현재 workload에서 시작할 우선순위다. 실제 `R_i`, `W_i`, coverage, migration을 계측하면 순위를 다시 계산한다.

| 모델 계열 | 첫 후보 | 뒤집는 조건 | 배치하지 않을 것 |
|---|---|---|---|
| Llama-3.1-8B GQA | 짧은 문맥은 shared weight page | `B×N×128 KiB`의 active-KV read가 weight read에 가까워질 때 KV로 전환. 재생 모델의 15.1 GB weight read 기준 교차점은 약 115k token-slots, B=8이면 N≈14.4k | 사용하지 않는 KV block, 곧 끝날 요청 |
| Qwen3-8B / Mistral-7B GQA | shared weight, 이어 active KV | Qwen은 144 KiB/token, Mistral은 128 KiB/token이므로 배치·문맥 증가에 따라 KV 점수를 재계산 | 모델 이름만 보고 KV 전부 고정 |
| Llama-2-7B MHA | active KV를 GQA보다 일찍 비교 | 512 KiB/token이라 B=8,N=2,048만으로 8 GiB payload. 측정 HBM KV read가 weight read를 넘으면 KV 우선 | 전체 checkpoint와 전체 KV를 동시에 고정하려는 정책 |
| Granite hybrid | **admission을 통과한 recurrent state**, 이어 attention KV/weight | state는 요청당 29,030,400 B이고 논리 R+W≈2×. 추가 640 MB tier에는 B=8도 들어가지만, 79.1 MiB L2 reservation에서는 B=8이 0.8259×였으므로 coverage 부족 시 no-admit | state라는 이유만으로 부분 보호를 강제 |
| Gemma-3 sliding/global attention | 현재 window KV와 global-layer KV, 이어 hot weights | 52개 sliding layer는 1,024 token에서 포화되고 10개 global layer만 계속 증가. 해당 부분의 실제 HBM read로 순위 결정 | window 밖에서 다시 읽지 않는 KV |
| gpt-oss-120b MoE | shared trunk와 route 확률이 높은 expert page, active KV | route distribution이나 phase가 바뀌면 expert score를 갱신. KV는 sliding/global 부분을 분리 | 전체 MoE checkpoint, cold experts |
| DeepSeek-V2-Lite MLA/MoE | 31,104 B/token의 latent KV를 완전히 덮는 후보와 shared/hot weight를 비교 | latent KV가 작아 완전 보호가 싸지만 baseline cache hit가 높으면 no-admit. 이후 route-weighted expert page | 펼친 MHA KV 크기로 잘못 계산, cold experts |

## 이 논문이 주장하지 않는 것

- B200의 L2가 제작된 3D SRAM과 같은 지연·에너지·열 특성을 가진다는 주장
- 1.1099×가 end-to-end LLM speedup이라는 주장
- 논리 read/write 바이트가 성능 카운터로 직접 센 HBM 바이트라는 주장
- 82.4%가 다른 캐시, 모델, 하드웨어에도 적용되는 보편 입장 임계값이라는 주장
- 모든 workload에서 state가 weight와 KV보다 먼저라는 주장

현재 실험은 배치 **메커니즘과 반례**를 검증했다. end-to-end serving 속도·에너지, 실제 3D SRAM PPA·thermal, runtime integration은 다음 증거다.

## prior work와 방어 가능한 차이

| 인접 연구 | 이미 해결한 것 | Ledger3D가 남길 차이 |
|---|---|---|
| [Cache-Resident LLM Inference](https://arxiv.org/abs/2606.25353) | GB-scale LLC에 weight를 상주시킨 CPU 실행 모델 | weight를 전제로 고정하지 않고 weight·KV·recurrent state의 한계 이득을 같은 단위로 비교 |
| [Dynamic KV Placement](https://arxiv.org/abs/2508.13231) | 이기종 메모리 사이 KV 배치의 수학적 상한 | KV 내부 배치에 더해 서로 다른 객체 종류가 하나의 빠른 tier를 놓고 경쟁하는 문제와 입장 거부 조건 |
| [AVMP](https://arxiv.org/abs/2605.22416) | hybrid Mamba/Transformer의 KV·SSM 용량 풀과 paging | 용량 낭비 대신 스텝별 off-chip traffic, read/write 비대칭, fast-tier 시간 이득을 목적함수로 사용 |
| [H3D-LLM](https://ieeexplore.ieee.org/document/11240702/) | 3D chiplet, KV-aware tiering, dynamic orchestration | 공개 원장·실제 GPU 대리 검증·객체별 반례를 결합한 재현 가능한 정책 도출 과정 |
| [3D-MoE](https://ieeexplore.ieee.org/document/11240872/) | MoE weight 배치와 3D near-memory architecture | MoE에 한정하지 않고 dense/GQA/MHA/MLA/sliding/SSM을 같은 원장으로 비교 |

“최초”는 systematic review가 끝나기 전에는 쓰지 않는다. 안전한 novelty는 **통합 객체 원장, admission-before-ranking 정책, B200에서 확인한 순위와 capacity-cliff의 동시 검증**이다.

## 네 편으로 나눌 때의 경계

### A. Ledger3D / 3D SRAM placement paper

- 질문: 제한된 stacked SRAM에 무엇을 넣어야 하는가?
- 고유 기여: 객체 원장, 입장+배치 정책, 모델별 전환 조건, B200 proxy와 end-to-end runtime 검증
- 추가 필수: serving-engine page placement, 실제 model workloads, latency/throughput/energy, 3D SRAM PPA·thermal point
- 현재 상태: 메커니즘과 반례는 닫힘. 시스템 성능 주장은 아직 열림.

### B. 2T0C gain-cell retention / KV quality paper

- 질문: retention·refresh 비용을 KV 중요도와 품질 제약에 맞춰 줄일 수 있는가?
- 고유 기여: retention binning, selective refresh/drop, matched random control, long-context accuracy
- Ledger3D와의 경계: 어떤 데이터를 보존할지와 품질이 핵심이고, 3D SRAM 배치 성능은 사용하지 않는다.

### C. ECTC package integration paper

- 질문: logic 위 3D memory를 어떤 bonding/TSV/power/thermal 조건으로 구현할 수 있는가?
- 고유 기여: package geometry, thermal/power-delivery/signaling co-design, manufacturable capacity point
- 필수: packaging tool 연동과 physical design evidence. B200 cache proxy만으로 제출하지 않는다.

### D. Ledger simulator / methodology paper

- 질문: 실제 trace와 구조식으로 새 모델·새 tier의 배치를 얼마나 정확히 예측할 수 있는가?
- 고유 기여: 공개 workload ledger schema, replay/scenario lab, calibration, prediction error across at least two platforms
- 독립 조건: A 논문의 그림 도구에 머물지 않고, 예측 정확도·속도·재현성 자체를 평가해야 한다.

공통 원자료를 공유하되, A는 placement 성능, B는 retention-quality, C는 physical package, D는 prediction methodology를 각각 주 결과로 둔다.

## 다음 실험의 통과 기준

1. 실제 serving engine에서 page 단위 weight/KV/state placement를 켜고 끌 수 있어야 한다.
2. 동일 request trace에서 default, weight-first, KV-first, state-first, admission-aware 정책을 비교한다.
3. TTFT·TPOT·throughput·joule/token과 품질을 함께 보고한다.
4. 짧은/긴 문맥, B=1/8/32, dense/MHA/SSM/sliding/MoE/MLA를 포함한다.
5. 예측한 순위와 실제 순위가 다르면 원장의 어떤 항이 빠졌는지 설명한다.
6. 추가 3D SRAM과 carved-cache proxy의 opportunity cost를 분리한다.

이 여섯 조건을 만족하면 “이 정책을 고려해 추론하면 빨라지고 에너지가 줄며 정확도는 유지된다”를 논문 결론으로 쓸 수 있다. 현재는 그 결론의 정책 원리와 B200 대리 검증까지 확보했다.
