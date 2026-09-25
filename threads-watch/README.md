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

## 데스크톱 PC 에서 자동 실행

준비물: git, Python 3.10 이상, Claude Code CLI(`claude` 명령, 로그인 완료). 추가 파이썬 패키지는 필요 없다.

1. 저장소 받기 (폴더 이름은 자유)
   ```bash
   git clone https://github.com/Kimseangtae/-.git robyn-threads
   cd robyn-threads
   ```
2. `threads-watch/channels.json` 에 감시 채널 추가.
3. 한 번 수동으로 돌려 확인
   - macOS: `bash threads-watch/run_local.sh`
   - Windows(PowerShell): `powershell -ExecutionPolicy Bypass -File threads-watch\run_local.ps1`
4. 예약 등록
   - **macOS**: 터미널에서 `crontab -e` 후 아래 한 줄 추가 (매일 08:00).
     `0 8 * * * /bin/bash /Users/사용자이름/robyn-threads/threads-watch/run_local.sh`
     경로는 실제 클론 위치로. PC 가 잠자기 상태면 실행되지 않으니 시스템 설정에서 예약 깨우기를 켠다.
   - **Windows**: 작업 스케줄러 → 기본 작업 만들기 → 트리거 "매일 08:00" → 동작 "프로그램 시작"
     프로그램: `powershell.exe`
     인수: `-ExecutionPolicy Bypass -File "C:\Users\사용자이름\robyn-threads\threads-watch\run_local.ps1"`
     조건 탭에서 "작업을 실행하기 위해 컴퓨터의 절전 모드 종료" 체크.
5. 결과 확인: `threads-watch/reports/` 의 날짜 파일, 실행 기록은 `threads-watch/logs/`.

스크립트는 최신 코드를 받고(git pull), Claude Code 에 스킬 절차 실행을 지시하고, 보고서를 커밋·푸시한다.
푸시가 되면 스마트폰에서도 GitHub 앱이나 브라우저로 보고서를 읽을 수 있다.

## 클라우드에서 자동 실행 (대안)
PC 를 켜두기 어렵다면 Claude Code Routine(예약 실행)이 정해진 시각에 클라우드 세션을 열어 같은 절차를 수행하고
`reports/` 에 커밋·푸시한다. 둘 중 하나만 켠다. 둘 다 켜면 같은 글을 두 번 분석한다.

## 데이터 출처와 한계
- 글 텍스트·게시 시각·URL 은 공개 RSSHub 미러(`fetch_threads.py` 의 `MIRRORS`)에서 가져온다.
  미러가 전부 막히면 WebFetch 로 프로필을 직접 읽는 대체 경로를 쓴다.
- 좋아요·답글·조회수는 가져오지 못한다. 분석은 글 구조 기준이다.
- 비공개 계정은 읽을 수 없다.
