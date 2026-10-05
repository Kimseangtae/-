<#
agents/status.ps1 — 중앙 PC 에서 큐·실행 중·완료·실패 현황을 본다.
  powershell -ExecutionPolicy Bypass -File agents\status.ps1
  powershell -ExecutionPolicy Bypass -File agents\status.ps1 -Last 20
  powershell -ExecutionPolicy Bypass -File agents\status.ps1 -Requeue 20260928-081000-threads-watch   # 죽은 PC 에 걸린 작업을 큐로 되돌림
#>
param(
  [int]$Last = 10,
  [string]$Requeue,
  [switch]$NoPull
)
$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo
$Branch = (git rev-parse --abbrev-ref HEAD).Trim()
$TasksDir = Join-Path $Repo "agents\tasks"
if (-not $NoPull) { git pull --rebase --autostash -q origin $Branch 2>&1 | Out-Null }

function Load([string]$Dir) {
  @(Get-ChildItem -Path (Join-Path $TasksDir $Dir) -Filter *.json -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
    try { Get-Content -Path $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
  })
}

if ($Requeue) {
  $src = Join-Path (Join-Path $TasksDir "running") "$Requeue.json"
  if (-not (Test-Path $src)) { Write-Error "running 에 없는 작업: $Requeue"; exit 1 }
  $t = Get-Content -Path $src -Raw -Encoding UTF8 | ConvertFrom-Json
  $t | Add-Member -NotePropertyName status -NotePropertyValue "queued" -Force
  $t | Add-Member -NotePropertyName last_error -NotePropertyValue ("requeued from " + $t.claimed_by) -Force
  $t.PSObject.Properties.Remove("claimed_by"); $t.PSObject.Properties.Remove("claimed_at")
  $dst = Join-Path (Join-Path $TasksDir "queue") "$Requeue.json"
  git mv -f $src $dst 2>&1 | Out-Null
  [System.IO.File]::WriteAllText($dst, ($t | ConvertTo-Json -Depth 8), $utf8)
  git add -A -- (Join-Path $TasksDir "queue") (Join-Path $TasksDir "running") 2>&1 | Out-Null
  git commit -q -m "requeue: $Requeue" 2>&1 | Out-Null
  git push origin $Branch 2>&1 | Out-Null
  Write-Host "큐로 되돌림: $Requeue"
  exit 0
}

$queue   = Load "queue"
$running = Load "running"
$done    = Load "done"
$failed  = Load "failed"

Write-Host ""
Write-Host ("대기 {0}  실행 중 {1}  완료 {2}  실패 {3}   ({4})" -f $queue.Count, $running.Count, $done.Count, $failed.Count, (Get-Date -Format "MM-dd HH:mm"))
Write-Host ""

if ($running.Count) {
  Write-Host "== 실행 중"
  $running | ForEach-Object {
    $mins = [int]((Get-Date) - [datetime]$_.claimed_at).TotalMinutes
    $limit = if ($_.timeout_min) { [int]$_.timeout_min } else { 60 }
    $flag = if ($mins -gt $limit + 5) { "  ← 제한 초과. PC 가 죽었을 수 있음. -Requeue 로 되돌리기" } else { "" }
    "  {0}  [{1}]  {2}분 경과{3}" -f $_.id, $_.claimed_by, $mins, $flag
  }
  Write-Host ""
}
if ($queue.Count) {
  Write-Host "== 대기"
  $queue | ForEach-Object { "  {0}  → {1}  재시도 {2}{3}" -f $_.id, $_.to, [int]$_.retries, $(if ($_.last_error) { "  (" + $_.last_error + ")" } else { "" }) }
  Write-Host ""
}
$recent = @($done + $failed | Where-Object { $_.finished_at } | Sort-Object { [datetime]$_.finished_at } -Descending | Select-Object -First $Last)
if ($recent.Count) {
  Write-Host "== 최근 결과 (최근 $Last 건)"
  $recent | ForEach-Object {
    $mark = if ($_.status -eq "done") { "성공" } else { "실패" }
    "  {0}  {1}  [{2}]  {3}  → {4}" -f ([datetime]$_.finished_at).ToString("MM-dd HH:mm"), $mark, $_.claimed_by, $_.id, $_.result_file
  }
  Write-Host ""
}
