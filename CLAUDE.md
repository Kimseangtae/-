# 로빈의밥상 작업 저장소

사용자는 유튜브 **로빈의밥상** 운영자 로빈님(Robyn 김성태). 항상 "로빈님"이라고 부르고, 한국어로 결론부터 짧게.
콘텐츠를 쓰기 전에 `gongu-lab/guidelines.md` 를 먼저 읽는다 (금지: 밥깡패 모든 형태 · 매실액 · 체칼 / 플랫폼별 호칭 / 단점 먼저 / 20년 셰프 1회 / 자리표시자 금지).

## 도구 지도
| 폴더 | 역할 | 스킬 |
|---|---|---|
| `gongu-lab/` | 공구: 레퍼런스 인스타 분석, 공구 일정 → 날짜별 제작, 지침 검사(`lint_content.py`), 유튜브 조사(`yt_research.py`) | gongu-lab |
| `content-hub/` | 일상 콘텐츠: 소재 수집·선별 → 플랫폼별 생성 → 카드뉴스·쇼츠 클립 → 예약 발행 → 성과·재활용, MCP | content-hub |
| `threads-watch/` | 자기계발·사업 레퍼런스 스레드 감시 → 실행 과제 | threads-watch |
| `.claude/skills/` | `/campaign-plan` `/draft-content` `/brand-review` `/performance-report` `/competitive-brief` | |

## 규칙
- 이 저장소는 **공개**다. 공구 일정·가격·초안(`gongu-lab/schedule.json`, `output/`, `calendar/`, `state/`, `content-hub/data/`, `content-hub/out/`)과 토큰 파일은 커밋하지 않는다. 마진·수익 구조는 어떤 파일에도 쓰지 않는다.
- 토큰·키·웹후크 주소는 채팅으로 받지 않는다. 각 도구의 `set-…` 명령으로 로컬에 저장.
- 제품 사실(가격·수량·마감·효능·단점)은 지어내지 않는다. 없으면 묻는다.
- 예약 승인(`hub.py queue approve`)과 발행(`hub.py run`)은 로빈님이 직접 한다.
- 파이썬: 윈도우는 `python`, 맥·리눅스는 `python3`.
