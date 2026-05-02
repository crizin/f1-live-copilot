# 🏎️ F1 Live Copilot

> [English README](README.md)

**AI와 함께 F1 경기를 실시간으로 관람하세요 — 해설자가 아닌, 같이 보는 친구로.**

F1 Live Copilot은 F1 공식 라이브 타이밍 데이터에 직접 연결하여, Claude Code 세션에서 실시간으로 경기를 함께 봅니다. 추월에 환호하고, 피트 전략을 분석하고, 세이프티카에 같이 긴장하는 — 진짜 친구 같은 AI 동료입니다.

> ⚠️ **개발 초기 단계** — 2026 시즌 중반 첫 공개 예정

## 왜 만들었나요?

스포츠는 혼자 보면 재미없잖아요. 같이 화면 보면서 소리 지를 사람, 언더컷이 완벽하게 먹혔을 때 같이 감탄할 사람, 5초 페널티에 같이 분노할 사람이 필요합니다.

F1 Live Copilot이 그 역할을 합니다.

**이것은 아닙니다:**
- 통계 대시보드 (F1 공식 앱을 쓰세요)
- 포지션 변화를 기계적으로 읽어주는 봇
- TV 중계를 대체하는 도구

**이것입니다:**
- 경기를 같이 보면서 진짜로 *이해하는* 친구
- 전략적 움직임을 포착하고 의견을 나누는 동료
- 당신의 에너지에 맞춰주는 동반자 — 흥분할 때 같이 흥분, 분석할 때 깊이 파고들기

## 동작 방식

```
나: /f1-live-copilot:start-f1

Copilot: F1 Live Timing 연결 중... 마이애미 GP 결승, Lap 1/57. 시작이다! 🏁

  [15랩 후]

Copilot: 아 SC 나왔다!! 근데 NOR이 2랩 전에 미디엄 새 타이어로 바꿨잖아.
         운 개좋은데?! 앞에 5명은 아직 1스틴트고...
         맥라렌이 잘 하면 P3까지 무료 점프 가능할 듯.

나: 해밀턴 오늘 좀 별로다

Copilot: ㅇㅇ 언더컷이 완전 안 먹었어 — LEC이 1랩 먼저 들어가서 바로 앞에서 나옴.
         근데 섹터2 타임 보면 페이스 자체는 나쁘지 않아.
         전략 판단 문제지 속도 문제는 아닌 듯. 페라리가 2스틴트에서
         전략 나눠서 갈 수도 있겠다.
```

## 아키텍처

```
서버 없음. 전부 로컬에서 실행.

/start-f1
  → 로컬 데몬이 F1 공식 SignalR WebSocket에 직접 연결
  → 델타 메시지로부터 전체 레이스 상태 관리
  → 이벤트 감지 (추월, 피트, 깃발, 패스티스트 랩)
  → 이벤트 → Claude Code Monitor → AI가 자연스럽게 반응
  → 전체 상황 스냅샷은 요청 시 읽기 (f1-live.md)
```

- **API 키 불필요** — F1 라이브 타이밍은 공개 엔드포인트
- **서버 비용 제로** — 전부 로컬 실행
- **데이터 재배포 없음** — F1 타이밍 페이지를 여는 것과 동일

## 설치

```bash
# 플러그인 추가
/plugin marketplace add crizin/f1-live-copilot

# 설치
/plugin install f1-live-copilot
```

**요구사항:** Python 3.10+, [uv](https://docs.astral.sh/uv/)

## 사용법

```bash
# F1 세션 중에 실행
/f1-live-copilot:start-f1
```

## 이벤트 감지

데몬이 감지하고 푸시하는 이벤트:

| 이벤트 | 감지 내용 |
|--------|----------|
| 추월 | 실제 트랙 위 추월 (피트 사이클 순위 변동은 필터) |
| 피트 인/아웃 | 누가 피트, 어떤 타이어, 몇 번째 스틴트 |
| 세이프티카 / VSC | 즉시 알림 + 전략적 영향 분석 |
| 패스티스트 랩 | 전체 최빠른 랩 갱신 |
| DNF / 리타이어 | 드라이버 레이스 종료 |
| 레이스 컨트롤 | 페널티, 조사, 트랙리밋, 깃발 |
| 트랙 상태 | 옐로, SC 투입, 레드 플래그, 클리어 |

이벤트는 5초 윈도우로 배칭되어 SC 리스타트 같은 혼잡한 순간에도 Claude가 과부하되지 않습니다.

## 개발

```bash
git clone https://github.com/crizin/f1-live-copilot
cd f1-live-copilot
uv sync

# 과거 레이스 데이터 다운로드
uv run dev/download-archive.py \
  --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" \
  -o dev/data/suzuka --skip-telemetry

# 50배속 리플레이
uv run dev/replay.py dev/data/suzuka/ --speed 50 --events-only

# 로컬 플러그인 테스트
claude --plugin-dir .
```

## 법적 고지

이 플러그인은 F1 공식 타이밍 페이지와 동일한 공개 라이브 타이밍 엔드포인트에 연결합니다. 데이터를 재배포하지 않으며, 각 사용자가 직접 연결합니다. [openf1.org](https://openf1.org), [Fast-F1](https://github.com/theOehrly/Fast-F1)과 유사한 방식입니다.

## 라이선스

MIT
