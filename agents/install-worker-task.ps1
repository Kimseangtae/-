<#
agents/install-worker-task.ps1 — 이 PC 에 worker 를 작업 스케줄러에 등록한다 (로그인하면 자동 시작, 죽으면 1분 뒤 재시작, 5분마다 큐 확인).
  등록:  powershell -ExecutionPolicy Bypass -File agents\install-worker-task.ps1
  해제:  powershell -ExecutionPolicy Bypass -File agents\install-worker-task.ps1 -Remove
"로그인한 사용자로 실행" 으로 등록한다. 스레드 로그인 프로필·셀렉츠 같은 화면이 필요한 프로그램을 쓰기 위해서다.
#>
param(
  [string]$TaskName = "RobynAgentWorker",
  [int]$IntervalSec = 300,
  [switch]$Remove
)
$ErrorActionPreference = "Stop"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "해제됨: $TaskName"
  exit 0
}
$worker = Join-Path $PSScriptRoot "worker.ps1"
$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$worker`" -Loop -IntervalSec $IntervalSec"
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "등록·시작됨: $TaskName  (컴퓨터 이름: $env:COMPUTERNAME, 확인 간격 ${IntervalSec}초)"
Write-Host "전원 옵션에서 '절전 모드 해제: 안 함' 으로 두어야 밤에도 돕니다."
