# 사무실 PC 3대 에이전트 구조 (로빈의밥상)

로빈님 사무실의 윈도우 PC 3대를 "중앙 1대 + 작업 PC" 구조로 묶는 방법입니다.
결론부터: **새 서버·큐 프로그램·포트 개방 없이, 지금 쓰는 GitHub 저장소를 작업 큐로 씁니다.**
이 폴더의 스크립트만 있으면 오늘 바로 돌아갑니다.

---

## 1. 받으신 조언, 어디까지 맞나

| 조언 | 판정 | 이유 |
|---|---|---|
| PC마다 에이전트, 한 대는 중앙 제어 | 맞음 | 이 문서 구조 그대로 |
| 중앙이 큐에 넣고 나머지가 받아 실행 | 맞음 | 단, 큐를 새로 깔 필요 없음. 저장소 폴더가 큐 |
| 윈도우끼리 PowerShell Remoting / WinRM | 2단계 | "지금 당장 깨우기" 용도로만. 방화벽·신뢰 호스트·계정 설정이 필요하고, 실패 재시도와 기록이 없음. PC 가 꺼져 있으면 명령이 그냥 사라짐 |
| 오래 도는 작업은 작업 스케줄러나 서비스 | 반만 맞음 | 작업 스케줄러는 맞음. **서비스는 안 됨.** 서비스는 로그인 없이 도는 방식이라 스레드 로그인 프로필, 셀렉츠, 프리미어처럼 화면이 있는 프로그램을 못 씀 → "로그인한 사용자로 실행" 으로 등록 |
| 공유 폴더 대신 HTTP API 나 메시지 큐 | 3단계 | 개발자 팀 규모에서 쓰는 방식. 1인 사무실 3대에는 과함. 저장소가 이미 큐·기록·재시도 역할을 다 함 |
| 세 대가 같은 IP 라 포트 충돌 → 내부 IP 고정, 포트 분배 | 오해 | 공유기 뒤에서 **외부 IP 는 같아도 내부 IP 는 PC 마다 다릅니다.** 포트 충돌은 서버를 열 때만 생기는데, 1단계 방식은 여는 포트가 0개. 내부 IP 고정은 2단계에서 공유기 DHCP 예약으로 하면 끝 |

## 2. 왜 저장소가 큐인가 (한계 먼저)

**한계**
- 즉시성이 없다. 작업 PC 가 5분마다 확인하므로 넣고 최대 5분 뒤 시작한다. (2단계 poke 로 즉시 가능)
- 초 단위로 수십 건을 넣는 용도가 아니다. 하루 수십 건까지가 적당하다.
- 작업 PC 저장소는 스크립트만 건드려야 한다. 손으로 고친 파일은 선점 충돌 시 버려질 수 있다.

**그럼에도 쓰는 이유**
- 이미 threads-watch 가 이 방식으로 돌고 있다. 새로 배울 게 없다.
- 넣은 작업, 누가 언제 했는지, 결과 전문이 전부 git 기록으로 남는다. 휴대폰 GitHub 앱으로도 본다.
- PC 가 꺼져 있어도 작업이 사라지지 않는다. 켜지면 가져간다.
- 실패하면 자동으로 큐에 되돌려 다시 시도한다. 시간 제한을 넘기면 강제 종료한다.
- 두 PC 가 같은 작업을 동시에 잡으면 git 이 한쪽을 거절한다. 진 쪽은 스스로 물러난다.

## 3. 구조

```
[중앙 PC]  dispatch.ps1 ── 작업 JSON ──▶ agents/tasks/queue/  (GitHub)
           status.ps1  ◀── 결과 md ────  agents/tasks/done/, failed/
                                              ▲
[작업 PC 1] worker.ps1 (5분마다 pull) ─ 내 몫 집어 running/ 으로 ─ run-one.ps1 로 실행 ─ 결과 push
[작업 PC 2] worker.ps1                     (to 가 내 이름이거나 "any")
```

| 파일 | 어디서 | 역할 |
|---|---|---|
| `agents.json` | 공통 | PC 명단. `name` 은 `hostname` 결과와 같아야 함 |
| `dispatch.ps1` | 중앙 | 작업을 큐에 넣고 push |
| `status.ps1` | 중앙 | 대기·실행 중·완료·실패 현황. 죽은 PC 에 걸린 작업 되돌리기 |
| `worker.ps1` | 작업 PC | 큐 확인 → 선점 → 실행 → 결과 push. `-Loop` 로 상주 |
| `run-one.ps1` | 작업 PC | 작업 하나를 별도 프로세스로 실행 (시간 제한·강제 종료용). 직접 부르지 않음 |
| `install-worker-task.ps1` | 작업 PC | worker 를 작업 스케줄러에 등록 (로그인 시 자동 시작, 죽으면 재시작) |
| `poke.ps1` | 중앙 (2단계) | 특정 PC 의 worker 를 즉시 깨움 |
| `prompts/*.txt` | 공통 | 자주 쓰는 긴 프롬프트 |
| `tasks/queue, running, done, failed` | 공통 | 작업 상태별 폴더. 작업 = JSON 1개, 결과 = 같은 이름의 md |

작업은 두 종류입니다.
- **prompt 작업**: Claude Code 에 프롬프트를 넘긴다 (`claude -p`). 스레드 분석, 글쓰기, 조사.
- **command 작업**: PowerShell 명령을 그대로 실행한다. 파이썬 스크립트, 인코딩, 파일 정리.

## 4. 설치 (PC 마다 한 번, 15분)

준비물은 threads-watch 와 같다: git, Python 3.10 이상, Claude Code CLI 로그인.

1. **컴퓨터 이름 정하기.** 각 PC 에서 PowerShell 을 열고 `hostname`. 나온 이름을 `agents.json` 에 적는다.
   바꾸고 싶으면 설정 → 시스템 → 정보 → "이 PC 의 이름 바꾸기" (재부팅). 예: PC-MAIN, PC-EDIT, PC-SUB.
2. **저장소 클론** (threads-watch 가 이미 있는 PC 는 `git pull` 만).
   ```powershell
   git clone https://github.com/Kimseangtae/-.git C:\Users\사용자이름\robyn-threads
   ```
   `agents.json` 의 `repo_path` 를 실제 경로로 맞춘다.
3. **작업 PC 마다 worker 등록.**
   ```powershell
   cd C:\Users\사용자이름\robyn-threads
   powershell -ExecutionPolicy Bypass -File agents\install-worker-task.ps1
   ```
   로그인하면 자동으로 시작되고, 죽으면 1분 뒤 다시 뜬다. 5분마다 큐를 본다.
   해제는 같은 명령에 `-Remove`.
4. **전원 설정.** 설정 → 시스템 → 전원 → 절전 모드 "안 함". 화면 끄기는 상관없다.
   자동 로그인까지 켜 두면 정전 후에도 혼자 복구된다 (`netplwiz` 에서 "사용자 이름과 암호 입력" 체크 해제).
5. **중앙 PC 도 worker 를 돌려도 된다.** 3대 다 일하게 하려면 중앙에도 3번을 한다.
6. **확인.** 중앙에서 작업 하나 넣고 5분 뒤 현황을 본다.
   ```powershell
   powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -To PC-EDIT -Title "설치 확인" -Prompt "지금 시각과 컴퓨터 이름을 한 줄로 알려줘" -AllowedTools "Bash(hostname*),Bash(date*)"
   powershell -ExecutionPolicy Bypass -File agents\status.ps1
   ```

## 5. 매일 쓰는 법 (중앙 PC)

**스레드 메소드 분석을 편집 PC 에** (로그인 프로필이 그 PC 에 있으므로 `-To` 를 꼭 지정)
```powershell
powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -To PC-EDIT -Title "threads-watch" -PromptFile agents\prompts\threads-watch.txt -TimeoutMin 40
```

**아무 PC 나 먼저 노는 PC 에 글쓰기**
```powershell
powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -Title "쇼츠 설명글 3편" -Prompt "threads-watch/reports 최신 보고서의 실행 과제 3개를 쇼츠 설명글 3편 초안으로. 결과는 drafts/shorts-YYYY-MM-DD.md 에 저장하고 커밋·푸시." -AllowedTools "Read,Write,Glob,Grep,Bash(git *)"
```

**Claude 없이 파이썬만, 3시간 제한**
```powershell
powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -To PC-SUB -Title "원본 변환" -Command "python tools\convert.py D:\원본\0928" -TimeoutMin 180 -MaxRetries 0
```

**현황 보기 / 죽은 PC 에 걸린 작업 되돌리기**
```powershell
powershell -ExecutionPolicy Bypass -File agents\status.ps1
powershell -ExecutionPolicy Bypass -File agents\status.ps1 -Requeue 20260928-081000-threads-watch
```

**매일 08:00 자동으로 넣기** (중앙 PC 작업 스케줄러에 한 번 등록)
```powershell
$repo = "C:\Users\사용자이름\robyn-threads"
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\agents\dispatch.ps1`" -To PC-EDIT -Title threads-watch -PromptFile `"$repo\agents\prompts\threads-watch.txt`" -TimeoutMin 40"
Register-ScheduledTask -TaskName "RobynDispatch-threads-watch" -Action $a -Trigger (New-ScheduledTaskTrigger -Daily -At 08:00) -Force
```
기존 `threads-watch/run_local.ps1` 예약이 편집 PC 에 있다면 둘 중 하나만 남긴다. 큐를 거치면 기록이 한곳에 모이므로 이쪽을 권한다.

`dispatch.ps1` 옵션: `-To`(기본 any) `-Title` `-Prompt` / `-PromptFile` / `-Command` `-Cwd`(저장소 기준 하위 폴더) `-AllowedTools` `-PermissionMode`(기본 acceptEdits) `-TimeoutMin`(기본 60) `-MaxRetries`(기본 1) `-NoPush`

## 6. 실패하면 어떻게 되나

| 상황 | 동작 |
|---|---|
| 종료 코드 0 이 아님 | `retries < max_retries` 면 10분 뒤 다시 큐에. 시도 기록은 `failed/<id>-try1.md` |
| 시간 제한 초과 | 프로세스 트리 강제 종료, 종료 코드 124 로 처리. 이후는 위와 같음 |
| 재시도 다 씀 | `failed/` 로. 결과 md 에 출력 전문 |
| 두 PC 가 같은 작업 선점 | git push 가 한쪽을 거절. 진 쪽은 원격 상태로 되돌리고 다음 작업 |
| 작업 PC 가 실행 중 꺼짐 | `running/` 에 남음. `status.ps1` 이 제한 시간 넘긴 건을 표시. `-Requeue` 로 되돌림 |
| 결과 push 실패 (인터넷 끊김) | 로컬 커밋으로 남아 다음 회차에 같이 push |
| 작업이 이미 실행 중인 PC 에 또 뜸 | 뮤텍스로 막음. 한 PC 에 worker 는 1개 |

완료·실패 시 그 PC 에 윈도우 알림이 뜬다. 중앙에서는 `status.ps1`, 밖에서는 휴대폰 GitHub 앱으로 `agents/tasks/done/` 을 본다.

## 7. 지켜야 할 규칙

- 작업 PC 저장소에서 손으로 파일을 고치지 않는다. 고칠 건 중앙 PC 나 클라우드 세션에서.
- `agents.json` 의 이름과 실제 `hostname` 이 다르면 그 PC 는 `-To` 지정 작업을 영원히 못 받는다. `any` 작업만 받는다.
- 로그인 프로필이 필요한 작업(스레드 답글 수집)은 반드시 그 PC 를 `-To` 로 지정한다.
- Claude 토큰·로그인은 PC 마다 따로다. `claude` 가 로그아웃되면 그 PC 의 prompt 작업은 전부 실패로 떨어진다. `failed/` 에 로그인 관련 문구가 보이면 그 PC 에서 `claude` 를 한 번 열어 다시 로그인.
- 작업 프롬프트에 결과를 어디에 저장하고 커밋·푸시하라는 말을 넣는다. 안 넣으면 결과는 `done/<id>.md` 의 출력 전문에만 남는다.

## 8. 2단계: 즉시 깨우기 (PowerShell Remoting)

5분 대기가 답답할 때만 한다. 하는 일은 딱 하나, 작업 PC 의 `agents\logs\poke` 파일을 원격으로 만들어 worker 를 바로 깨우는 것.

1. **공유기에서 내부 IP 고정.** 공유기 관리 페이지 → DHCP 예약(또는 "고정 할당") → 각 PC 의 MAC 주소에 IP 하나씩. 예: 192.168.0.11 / 12 / 13.
2. **작업 PC 마다** (관리자 PowerShell): `Enable-PSRemoting -Force`
   네트워크 프로필이 "공용" 이면 실패한다. 설정 → 네트워크 → 이더넷 → "개인 네트워크" 로 바꾼 뒤 다시.
3. **중앙 PC 에서** (관리자 PowerShell): `Set-Item WSMan:\localhost\Client\TrustedHosts -Value "PC-EDIT,PC-SUB" -Force`
4. 세 PC 의 윈도우 로그인 계정과 비밀번호가 같아야 한다 (같은 Microsoft 계정이면 됨). 비밀번호 없는 계정은 안 된다.
5. 확인: `Invoke-Command -ComputerName PC-EDIT -ScriptBlock { hostname }`
6. 이후 `dispatch` 뒤에 `powershell -ExecutionPolicy Bypass -File agents\poke.ps1 -Pc PC-EDIT`.

포트는 WinRM 이 쓰는 5985 하나뿐이고, 사무실 내부망에서만 열린다. PC 마다 포트를 나눌 일은 없다.

## 9. 3단계: HTTP API / 메시지 큐로 가는 조건

아래 중 둘 이상이 생기면 그때 간다. 지금은 해당 없음.
- 하루 작업이 100건을 넘는다.
- 사무실 밖(외주 편집자, 다른 지역 PC)에서 작업을 받아야 한다.
- 작업 결과를 바로 다른 프로그램(대시보드, 알림톡)이 받아야 한다.
- 팀에 개발자가 한 명 이상 있다.

그때도 이 폴더의 작업 JSON 형식은 그대로 두고, 저장 위치만 저장소에서 API 로 바꾸면 된다.

## 10. PC 가 필요 없는 작업은 클라우드로

로그인 프로필이나 로컬 파일이 필요 없는 작업(글쓰기, 조사, 보고서 정리)은 PC 큐에 넣지 않아도 된다.
Claude Code 클라우드 세션의 예약 실행(Routine)이 저장소를 직접 받아 돌리고 push 한다. PC 가 전부 꺼져 있어도 된다.
PC 큐는 **로컬 자원이 필요한 작업**(스레드 로그인, 영상 원본, 셀렉츠·프리미어, GPU) 전용으로 두면 역할이 깔끔하다.
