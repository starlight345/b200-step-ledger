# 디코드 상주 3D 원장 — B200 기록 보관소

GitHub Pages에서 서버 없이 여는 정적 보관판입니다.

- `index.html`: 설명 글과 영상
- `replay.html`: B200 녹화 인터랙티브 재생
- `scenario-lab.html`: 녹화 없이 모델·배치·문맥·배치 정책을 바꾸는 one-step memory traffic simulator
- `assets/b200_replay.json`: 원본 JSONL에서 만든 359,118 B (350.701 KiB) 델타 파생물
- `assets/b200_walkthrough.mp4`: 약 6분 5초 한국어 음성 해설 영상. 핵심 용어, 직렬 합·완전 겹침의 상하한, 모델 맞추기·가중치 적재 대기, 3D SRAM·HBF 포함/제외, 여덟 모델의 B200 검산 범위를 실제 UI로 설명
- `assets/b200_walkthrough.ko.vtt`: 켜고 끌 수 있는 한국어 자막
- `assets/model_evidence.json`: 여덟 모델의 구조, 측정 종류, 원자료 경로와 SHA-256 파일 지문을 기계가 읽을 수 있게 정리한 증거표
- `vendor/three.min.js`: 인터넷이 없어도 3D 장면이 열리도록 저장한 로컬 three.js

원본 `b200_raw_20260913.jsonl`은 용량과 연구 데이터 보존을 위해 암페어에 남겨 두며 이 디렉터리에 복사하지 않습니다.

로컬 확인:

```bash
python3 -m http.server 4173
```

그 뒤 `http://localhost:4173/`을 엽니다. `file://`로 직접 열면 브라우저의 `fetch` 보안 규칙 때문에 녹화 JSON을 읽지 못할 수 있습니다.

## 메모리·수치 근거 보완 (2026-09-16)

- `memory.html`: 데이터 내용·수명, 단위, 유효 KV/블록 슬롯/예약 풀 구분, 대화형 계산기, 수치별 근거와 반납 전 수집 항목.
- `assets/numerical_evidence.json`: 설명용 입력값과 계산값, 원자료 파일명 및 SHA-256.
- `assets/model_evidence.json` v2: nb1 완료 간격 60개 집계 방법, 예산/슬롯 역산과 텐서 덤프 구분, Granite DCGM 추정 범위 정정.
- 재생판: 현재 데이터별 정확한 바이트 표, 미계측 항목 표시. L2 사본을 본거지 저장량에 중복 가산하지 않으며 가상 SRAM 배치에서도 L2 용량을 빼지 않음. 확대 그래프의 L2 선은 용량 비교선.
- 기존 영상은 이전 설명판이므로 최신 측정 방법과 증거 등급은 `memory.html`을 기준으로 읽는다.

현재 화면의 객체별 읽기/쓰기와 가상 메모리 시간은 계산값이다. 중간값·작업 공간·런타임 여유와 실제 R/W 카운터 검증은 미완료이며, 배치 가능 판정은 지속 데이터에 대한 필요조건이다. 전체 실행 가능 여부를 보증하지 않는다.


## B200 배치 검증 (2026-09-16)

- 동일한 64 MiB weight·KV·state를 실제 B200 persisting L2에 하나씩 배치한 사전등록 통제 실험.
- 물리 GPU 2개, GPU당 90 trial, validation 오류 0.
- 통합 기하평균: weight `1.0554×`, KV `1.0562×`, state `1.1099×` (matched default 대비).
- Granite-state 용량 실험은 작은 상태에서 최대 `1.1364×`, 보호 용량을 넘긴 B=8에서 `0.8259×`로 역전됨.
- `assets/placement_evidence.json`: 공개 요약과 주장 경계.
- `assets/experiments/ledger3d_placement_20260916/`: 사전등록, CUDA source, raw JSONL, 두 GPU summary와 해시.
- `assets/experiments/cache_policy_20260916/`: 용량/간섭 sweep의 사전등록, source, raw JSONL, summary와 telemetry.

이 검증은 실제 B200 L2에서 배치 순위를 측정한 대리 실험이다. 제작된 3D SRAM의 PPA·열 특성이나 end-to-end vLLM 배치 구현으로 표시하지 않는다.
