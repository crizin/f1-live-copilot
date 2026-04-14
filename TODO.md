# TODO

## Next Up
- [ ] Monitor 연동 실제 테스트 (스킬 → 데몬 → Monitor → Claude 해설 end-to-end)
- [ ] `bin/f1-daemon` 실행 스크립트 작성 (uv run wrapper, PATH에 추가되는 용도)
- [ ] 이벤트 감지 세부 튜닝
  - [ ] 블루플래그 반복 메시지 필터 (같은 차에 대해 N초 내 중복 무시)
  - [ ] 피트 아웃 시 타이어 `UNKNOWN` 케이스 개선 (Stints 데이터 타이밍 이슈)
  - [ ] RC 메시지 중 노이즈 추가 필터 (WAVED BLUE FLAG 등)
- [ ] 마이애미 GP (5/1~3) 라이브 테스트

## Personas
- [ ] `references/personas/expert.md` — 전문 해설위원 (전략/타이어 디그레이드/언더컷 분석)
- [ ] `references/personas/girlfriend.md` — F1 입문한 여자/남자친구
- [ ] `references/personas/toxic.md` — 과격한 욕쟁이 커뮤니티 이용자
- [ ] `references/personas/data-nerd.md` — 통계 덕후
- [ ] `references/personas/casual.md` — 편하게 보는 친구 (큰 이벤트만)
- [ ] SKILL.md에 $ARGUMENTS 기반 페르소나 선택 로직 추가

## Polish
- [ ] 추가 GP 데이터 다운로드 & 리플레이 검증 (호주, 중국)
- [ ] Qualifying/Sprint 세션 지원 (현재 Race 위주)
- [ ] 챔피언십 스탠딩 추적 (누적 포인트)
- [ ] 날씨 변화 이벤트 감지 (비 시작/멈춤)

## Release
- [ ] GitHub repo 생성 & push
- [ ] 마켓플레이스 등록 테스트
- [ ] LICENSE 파일 추가
- [ ] Reddit/커뮤니티 홍보
