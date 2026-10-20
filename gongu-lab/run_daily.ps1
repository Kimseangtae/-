# Windows 용. 매일 아침 예약 실행: 오늘·내일 올릴 콘텐츠를 만들어 두고 오늘 할 일을 알려준다.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

$logDir = "gongu-lab\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("daily_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmm"))

"== $(Get-Date) 시작" | Tee-Object -FilePath $log -Append
git pull --ff-only 2>&1 | Tee-Object -FilePath $log -Append
python gongu-lab\plan_calendar.py plan 2>&1 | Tee-Object -FilePath $log -Append

$prompt = "gongu-lab 스킬(.claude/skills/gongu-lab/SKILL.md)의 모드 B 를 수행해라. 먼저 plan_calendar.py today 를 실행하고, 오늘과 내일 항목 중 미작성인 것을 brief 로 지시서를 받아 guidelines.md 와 analysis/ 의 최신 분석을 따라 작성해라. 작성한 파일은 lint_content.py 오류 0건이 될 때까지 고쳐라. 제품 정보(가격·수량·단점·마감)가 schedule.json 에 없으면 지어내지 말고 그 항목을 건너뛰고 무엇이 필요한지 마지막에 적어라. 끝나면 gongu-lab 을 커밋·푸시하고, 마지막에 오늘 올릴 것 목록과 파일 경로, 필요한 정보 목록을 출력해라. 파이썬은 python 명령을 써라."

claude -p $prompt `
  --permission-mode acceptEdits `
  --allowedTools "Read,Write,Edit,Glob,Grep,Agent,Bash(python *),Bash(python3 *),Bash(git *)" `
  --output-format text 2>&1 | Tee-Object -FilePath $log -Append

"== $(Get-Date) 끝" | Tee-Object -FilePath $log -Append

try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $t = $xml.GetElementsByTagName("text"); $t.Item(0).AppendChild($xml.CreateTextNode("로빈의밥상 gongu-lab")) | Out-Null
  $t.Item(1).AppendChild($xml.CreateTextNode("오늘 올릴 공구 콘텐츠가 준비됐습니다")) | Out-Null
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Code").Show([Windows.UI.Notifications.ToastNotification]::new($xml))
} catch {}
