# threads-watch

로빈의밥상용 스레드 레퍼런스 채널 감시 도구. 감시 채널에 새 글이 올라오면
분석해 보고하고, 차용할 부분을 로빈의밥상 스레드 글로 바꿔 적용안을 만든다.

## 구성
| 파일 | 역할 |
|---|---|
| `channels.json` | 감시할 채널 목록 |
| `fetch_threads.py` | 새 글 가져오기 + 본 글 기록 |
| `state/seen.json` | 이미 본 글 ID (자동 갱신) |
| `reports/` | 날짜별 보고서 |
| `../.claude/skills/threads-watch/SKILL.md` | 분석·차용 절차 |

## 채널 추가
`channels.json` 의 `channels` 배열에 한 줄 추가:
```json
{ "handle": "핸들", "enabled": true, "memo": "왜 보는지 한 줄" }
```
핸들은 `@` 없이. 프로필 URL 을 그대로 넣어도 스크립트가 정리한다.

## 수동 실행
```bash
python3 threads-watch/fetch_threads.py --handle 핸들   # 시험 (기록 안 함)
python3 threads-watch/fetch_threads.py --mark           # 새 글 출력 + 기록
```
그다음 Claude Code 에서 "스레드 감시 돌려줘" 라고 하면 SKILL.md 절차대로 보고서를 만든다.

## 자동 실행
Claude Code Routine(예약 실행)이 정해진 시각에 새 세션을 열어 위 절차를 수행하고
`reports/` 에 커밋·푸시한다. 주기 변경은 Routine 설정에서.

## 데이터 출처와 한계
- 글 텍스트·게시 시각·URL 은 공개 RSSHub 미러(`fetch_threads.py` 의 `MIRRORS`)에서 가져온다.
  미러가 전부 막히면 WebFetch 로 프로필을 직접 읽는 대체 경로를 쓴다.
- 좋아요·답글·조회수는 가져오지 못한다. 분석은 글 구조 기준이다.
- 비공개 계정은 읽을 수 없다.
