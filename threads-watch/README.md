# threads-watch

로빈님의 **자기계발·사업 확장용** 스레드 레퍼런스 감시 도구.
감시 채널에 새 글이 올라오면 본문과 작성자 답글까지 읽고, 그 안의 메소드·원칙을 뽑아
로빈님 사업(유튜브, 공동구매, 브랜드 협업, 멤버십, 업무 시스템, 확장)에 맞는 **실행 과제**로 바꾼다.
글쓰기 형식을 베끼는 도구가 아니다.

## 왜 데스크톱인가
레퍼런스 채널들은 "본문 1~3개 + 나머지는 작성자 답글" 구조가 흔하다. 스레드는 로그인 없이는 답글을
내주지 않으므로, 로빈님 PC 의 로그인된 브라우저 프로필로 읽어야 메소드 전체가 잡힌다.

## 구성
| 파일 | 역할 |
|---|---|
| `channels.json` | 감시 채널 목록 |
| `fetch_threads.py` | 새 글 목록 (RSS, 로그인 불필요) + 본 글 기록 |
| `fetch_thread_full.py` | 글 하나의 본문 + 작성자 답글 전체 (로그인 프로필 사용) → `raw/` |
| `state/seen.json` | 이미 본 글 ID (자동) |
| `raw/` | 글별 원문 저장 |
| `reports/` | 날짜별 메소드 보고서 |
| `methods.md` | "지금 적용" 메소드 누적 목록과 실행 상태 |
| `run_local.sh` / `run_local.ps1` | PC 자동 실행 스크립트 |
| `../.claude/skills/threads-watch/SKILL.md` | 분석·적용 절차 |

## PC 설치 (한 번만)
준비물: git, Python 3.10 이상, Claude Code CLI(`claude`, 로그인 완료).

```bash
git clone https://github.com/Kimseangtae/-.git robyn-threads
cd robyn-threads
pip install playwright
python3 -m playwright install chromium        # Windows 는 python
python3 threads-watch/fetch_thread_full.py --login
```
마지막 명령으로 열리는 창에서 스레드에 로그인한 뒤 터미널에서 Enter. 로그인 정보는 `threads-watch/.browser-profile/` 에
PC 안에만 저장되고 git 에는 올라가지 않는다.

## 매일 쓰기
- 수동: 저장소 폴더에서 `claude` 를 열고 **"스레드 메소드 분석 돌려줘"**. 스킬이 새 글 확인 → 답글 수집 → 메소드 추출 → 실행 과제 → 보고서 저장·푸시까지 한다.
- 자동: 아래 예약 등록.

### 예약 등록 (매일 08:00)
- **macOS**: `crontab -e` 에 한 줄. 경로는 실제 클론 위치로.
  `0 8 * * * /bin/bash /Users/사용자이름/robyn-threads/threads-watch/run_local.sh`
- **Windows**: 작업 스케줄러 → 기본 작업 만들기 → 매일 08:00 → 프로그램 `powershell.exe`,
  인수 `-ExecutionPolicy Bypass -File "C:\Users\사용자이름\robyn-threads\threads-watch\run_local.ps1"`.
  조건 탭 "작업을 실행하기 위해 컴퓨터의 절전 모드 종료" 체크.

결과는 `reports/날짜.md`, 누적은 `methods.md`, 실행 기록은 `logs/`. 푸시되면 휴대폰에서도 GitHub 로 읽을 수 있다.

## 채널 추가
`channels.json` 의 `channels` 에 `{ "handle": "핸들", "enabled": true, "memo": "왜 보는지" }` 추가. `@` 없이.

## 한계
- 좋아요·답글 수 등 반응 수치는 가져오지 않는다.
- 로그인 세션이 만료되면 답글 수집이 실패한다. `--login` 을 다시 실행하면 된다.
- 로빈님 개인 계정으로 로빈님이 볼 수 있는 글을 하루 몇 건 읽는 용도다. 대량 수집에 쓰지 않는다.

## 클라우드 예약
답글을 읽으려면 로그인 프로필이 필요해 클라우드 실행은 꺼 두었다. PC 를 쓸 수 없는 기간에만 켠다.
