# 디코드 상주 3D 원장 — B200 기록 보관소

GitHub Pages에서 서버 없이 여는 정적 보관판입니다.

- `index.html`: 설명 글과 영상
- `replay.html`: B200 녹화 인터랙티브 재생
- `assets/b200_replay.json`: 원본 JSONL에서 만든 351 KB 델타 파생물
- `assets/b200_walkthrough.mp4`: 97초 한국어 음성 해설 영상
- `assets/b200_walkthrough.ko.vtt`: 켜고 끌 수 있는 한국어 자막
- `vendor/three.min.js`: 인터넷이 없어도 3D 장면이 열리도록 저장한 로컬 three.js

원본 `b200_raw_20260913.jsonl`은 용량과 연구 데이터 보존을 위해 암페어에 남겨 두며 이 디렉터리에 복사하지 않습니다.

로컬 확인:

```bash
python3 -m http.server 4173 --directory ledger3d_pages
```

그 뒤 `http://localhost:4173/`을 엽니다. `file://`로 직접 열면 브라우저의 `fetch` 보안 규칙 때문에 녹화 JSON을 읽지 못할 수 있습니다.
