# Windows 용. PowerShell 에서 실행하거나 작업 스케줄러에 등록한다.
# 하는 일: 최신 코드 받기 → Claude Code 에 threads-watch 스킬 실행 지시 → 보고서 커밋·푸시
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$logDir = "threads-watch\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmm"))

"== $(Get-Date) 시작" | Tee-Object -FilePath $log -Append
git pull --ff-only 2>&1 | Tee-Object -FilePath $log -Append

$prompt = "threads-watch 스킬(.claude/skills/threads-watch/SKILL.md)의 실행 순서를 1번부터 7번까지 그대로 수행해라. 새 글마다 fetch_thread_full.py 로 답글까지 가져와라. 새 글이 없으면 한 줄만 남기고 끝내라. 새 글이 있으면 메소드 보고서를 threads-watch/reports/ 에 저장하고 methods.md 를 갱신하고 커밋·푸시까지 마쳐라. 마지막에 판정 표와 실행 과제를 출력해라. 파이썬은 python 명령을 써라."

claude -p $prompt `
  --permission-mode acceptEdits `
  --allowedTools "Read,Write,Edit,Glob,Grep,WebFetch,Bash(python *),Bash(python3 *),Bash(git *)" `
  --output-format text 2>&1 | Tee-Object -FilePath $log -Append

"== $(Get-Date) 끝" | Tee-Object -FilePath $log -Append

# 완료 알림 (Windows 토스트)
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $t = $xml.GetElementsByTagName("text"); $t.Item(0).AppendChild($xml.CreateTextNode("로빈의밥상 threads-watch")) | Out-Null
  $t.Item(1).AppendChild($xml.CreateTextNode("스레드 레퍼런스 보고서가 준비됐습니다")) | Out-Null
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Code").Show([Windows.UI.Notifications.ToastNotification]::new($xml))
} catch {}
