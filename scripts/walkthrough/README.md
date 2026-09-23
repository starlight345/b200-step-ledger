# 설명 영상 v2 녹화 도구

`scripts/build_walkthrough_v2.cjs`를 대신해 이 저장소의 정적 페이지를 실제로
조작하며 녹화하고, 한국어 음성·자막·포스터까지 한 번에 만든다.

## 왜 .cjs 대신 이 도구인가

`build_walkthrough_v2.cjs`는 이 맥에서 실행할 수 없다.

- playwright의 화면 녹화기는 `-c:v vp8`로 고정돼 있고 확장자도 `.webm`만 받는다.
  (`playwright-core/lib/server/chromium/videoRecorder.js`)
- 이 맥에 있는 유일한 ffmpeg는 playwright가 받아 둔
  `~/Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac`이고, 인코더가 PNG와
  libvpx VP8 두 개뿐이다. H.264도 오디오 인코더도 없다.
- 즉 녹화본이 VP8 WebM으로 나오는데, 이 기계에는 VP8을 **디코드**할 수단도 없어
  MP4로 옮길 방법이 없다. Homebrew도 없다.

그래서 화면은 Chrome에 CDP로 직접 붙어 받고, 인코딩은 시스템 프레임워크로 한다.
추가 설치가 필요 없고, 맥에 이미 있는 것만 쓴다.

| 단계 | 쓰는 것 |
|---|---|
| 화면 조작·녹화 | Chrome + CDP (`cdp.py`, 표준 라이브러리만 쓴 WebSocket 클라이언트) |
| 한국어 음성 | `/usr/bin/say` · Yuna · 178 wpm |
| 오디오 이어붙이기 | `wave` 표준 모듈 + `/usr/bin/afconvert` (AAC) |
| H.264/AAC MP4 | `Encode.m` · AVFoundation (`clang`으로 빌드) |
| 확인용 스틸 | `Grab.m` |

Objective-C인 이유는 이 기계의 Command Line Tools에 `SwiftBridging` 모듈 맵이
중복 정의돼 있어 `swiftc`가 동작하지 않기 때문이다.

## 쓰는 법

```bash
# 대본에 적힌 화면 요소가 지금 페이지에 모두 있는지만 확인 (녹화 안 함)
./build.py --check

# 전체 녹화
./build.py

# 바뀐 장면만 다시 녹화
./build.py --scenes 04,05

# 저장소를 건드리지 않고 시험 렌더
./build.py --out-dir /tmp/시험 --prefix draft
```

기본 출력은 `assets/b200_walkthrough_v2.{mp4,ko.vtt}`,
`assets/b200_walkthrough_v2_poster.png`,
`assets/b200_walkthrough_v2.build.json`이다.

## 화면이 바뀌면

`storyboard.py`가 장면별 화면 조작을 들고 있고, 각 장면의 길이는
`assets/b200_walkthrough_narration_v2.ko.txt`를 읽어 실제 음성 길이로 정한다.
계획표의 예상 길이가 아니라 측정된 음성 길이에 화면을 맞추므로, 대본을 고치면
화면 길이도 따라 바뀐다.

버튼 이름이나 id가 바뀌면 `--check`가 먼저 알려 준다. 녹화 중에도 요소를 찾지
못하면 조용히 엉뚱한 화면을 찍지 않고 그 자리에서 실패한다.

## 확인 사항

- 녹화 중 페이지에서 콘솔 오류가 나면 빌드가 실패한다(favicon 404는 제외).
- 정적 서버는 빈 포트를 골라 띄우고, 그 포트가 정말 이 작업 트리를 서비스하는지
  `index.html` 바이트를 비교해 확인한다. 이 기계에서는 여러 세션이 4173·4174 같은
  포트를 이미 쓰고 있어, 확인 없이는 다른 체크아웃을 녹화할 수 있다.
- `build.json`의 `audioVideoDriftSeconds`로 음성과 화면 길이 차이를 남긴다.
- 렌더 결과는 `./grab 영상.mp4 /tmp/확인 30 90 150`으로 해당 시각 화면을 꺼내
  대본이 말하는 화면이 맞는지 눈으로 본다.

## 출력 크기

720p 화면 녹화는 정지 구간이 많아 잘 압축된다. 기본 700 kbps에서 6분 기준 약
33 MB이고, 500 kbps에서도 3D 장면 위의 작은 한글이 읽힌다. v1 영상은 13 MB였으므로
더 줄여야 하면 `--bitrate`로 낮춘다.
