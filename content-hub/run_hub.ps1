# Windows 작업 스케줄러용: 15분마다 예약 시각이 된 글을 발행하고, 손으로 올릴 것은 휴대폰·윈도우 알림으로 알린다.
# 등록(관리자 아닌 PowerShell 에서 한 번):
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$HOME\Documents\robyn-threads\content-hub\run_hub.ps1`""
#   $t = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
#   Register-ScheduledTask -TaskName "robyn-content-hub" -Action $a -Trigger $t
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force -Path "content-hub\logs" | Out-Null
$log = "content-hub\logs\run_{0}.log" -f (Get-Date -Format "yyyy-MM-dd")
$out = python content-hub\hub.py run 2>&1 | Out-String
"== $(Get-Date)`n$out" | Add-Content -Path $log -Encoding utf8
if ($out -match "올릴 것") {
  try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $t = $xml.GetElementsByTagName("text"); $t.Item(0).AppendChild($xml.CreateTextNode("로빈의밥상 content-hub")) | Out-Null
    $t.Item(1).AppendChild($xml.CreateTextNode("올릴 시간이 된 글이 있습니다 (로그 확인)")) | Out-Null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Code").Show([Windows.UI.Notifications.ToastNotification]::new($xml))
  } catch {}
}
