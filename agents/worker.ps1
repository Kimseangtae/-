<#
agents/worker.ps1 — 작업 PC 에이전트.
저장소 agents/tasks/queue 에서 내 몫("to" 가 내 컴퓨터 이름이거나 "any")인 작업을 하나 집어 running 으로 옮기고(선점),
run-one.ps1 로 실행한 뒤 결과를 done/ 또는 failed/ 에 남기고 푸시한다. 실패하면 max_retries 까지 큐로 되돌린다.

  한 번만:  powershell -ExecutionPolicy Bypass -File agents\worker.ps1
  상주:     powershell -ExecutionPolicy Bypass -File agents\worker.ps1 -Loop -IntervalSec 300
            (install-worker-task.ps1 이 이 상주 모드를 작업 스케줄러에 등록한다)
  즉시 깨우기: agents\logs\poke 파일을 만들면 대기 중이던 상주 worker 가 바로 큐를 본다 (poke.ps1 참고).

규칙: worker PC 의 저장소는 이 스크립트만 건드린다. 손으로 파일을 고치지 않는다 (선점 충돌 시 원격 상태로 되돌리기 때문).
#>
param(
  [string]$Me = $env:COMPUTERNAME,
  [switch]$Loop,
  [int]$IntervalSec = 300,
  [int]$MaxTasksPerRound = 3
)
$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$Repo     = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TasksDir = Join-Path $Repo "agents\tasks"
$LogDir   = Join-Path $Repo "agents\logs"
$PokeFile = Join-Path $LogDir "poke"
foreach ($d in @($LogDir, "queue", "running", "done", "failed")) {
  $p = if ($d -eq $LogDir) { $d } else { Join-Path $TasksDir $d }
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}
Set-Location $Repo
$Branch = (git rev-parse --abbrev-ref HEAD).Trim()

function Now { Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz" }
function Log([string]$Msg) {
  $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Me, $Msg
  Write-Host $line
  Add-Content -Path (Join-Path $LogDir ("worker-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))) -Value $line -Encoding UTF8
}
function Read-Json([string]$Path) { Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
function Write-Json([string]$Path, $Obj) {
  $json = $Obj | ConvertTo-Json -Depth 8
  # PowerShell 5.1 은 한글을 \uXXXX 로 바꿔 저장한다. 읽기 좋게 되돌린다 (제어문자·따옴표·역슬래시는 그대로 둔다).
  $json = [regex]::Replace($json, '(?<!\\)((?:\\\\)*)\\u([0-9a-fA-F]{4})', {
    param($m)
    $c = [Convert]::ToInt32($m.Groups[2].Value, 16)
    if ($c -lt 0x20 -or $c -eq 0x22 -or $c -eq 0x5C) { return $m.Value }
    return $m.Groups[1].Value + [string][char]$c
  })
  [System.IO.File]::WriteAllText($Path, $json, $utf8)
}
function Set-Field($Obj, [string]$Name, $Value) { $Obj | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force }

function Sync-Repo {
  $out = git pull --rebase --autostash origin $Branch 2>&1
  if ($LASTEXITCODE -ne 0) {
    Log "git pull 실패: $out"
    git rebase --abort 2>&1 | Out-Null
    return $false
  }
  return $true
}
function Push-Repo([string]$Message) {
  for ($i = 1; $i -le 5; $i++) {
    git add -A 2>&1 | Out-Null
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { git commit -q -m $Message 2>&1 | Out-Null }
    $out = git push origin $Branch 2>&1
    if ($LASTEXITCODE -eq 0) { return $true }
    Log "push 실패 ($i/5), 원격 변경을 받아 재시도: $out"
    git pull --rebase --autostash origin $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { git rebase --abort 2>&1 | Out-Null; return $false }
    Start-Sleep -Seconds (3 * $i)
  }
  return $false
}

function Claim-Task {
  if (-not (Sync-Repo)) { return $null }
  $now = Get-Date
  $candidates = @(Get-ChildItem -Path (Join-Path $TasksDir "queue") -Filter *.json | Sort-Object Name | ForEach-Object {
    try { $t = Read-Json $_.FullName } catch { Log "손상된 작업 파일 건너뜀: $($_.Name)"; return }
    if ($t.to -ne "any" -and $t.to -ne $Me) { return }
    if ($t.retry_after -and ([datetime]$t.retry_after) -gt $now) { return }
    [pscustomobject]@{ File = $_; Task = $t }
  })
  if ($candidates.Count -eq 0) { return $null }
  $pick = $candidates[0]
  $t = $pick.Task
  Set-Field $t "status"     "running"
  Set-Field $t "claimed_by" $Me
  Set-Field $t "claimed_at" (Now)
  $dest = Join-Path (Join-Path $TasksDir "running") $pick.File.Name
  git mv -f $pick.File.FullName $dest 2>&1 | Out-Null
  Write-Json $dest $t
  if (Push-Repo ("agent: {0} 시작 — {1}" -f $t.id, $Me)) { return @{ Path = $dest; Task = $t } }
  # 다른 PC 가 같은 작업을 먼저 가져간 경우. 내 변경을 버리고 원격 상태로 되돌린다.
  Log "작업 $($t.id) 선점 실패 (다른 PC 가 먼저 가져감). 원격 상태로 되돌림"
  git rebase --abort 2>&1 | Out-Null
  git fetch origin $Branch 2>&1 | Out-Null
  git reset -q --hard "origin/$Branch" 2>&1 | Out-Null
  return $null
}

function Run-Task([string]$Path, $t) {
  $id = [string]$t.id
  $title = if ($t.title) { [string]$t.title } else { $id }
  $timeoutMin = if ($t.timeout_min) { [int]$t.timeout_min } else { 60 }
  $outFile = Join-Path $LogDir "$id.out.txt"
  if (Test-Path $outFile) { Remove-Item $outFile -Force }
  $runner = Join-Path $PSScriptRoot "run-one.ps1"
  $started = Get-Date
  Log "실행 시작: $id ($title), 제한 ${timeoutMin}분"

  $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$runner`"", "-TaskFile", "`"$Path`"", "-OutFile", "`"$outFile`"")
  $sp = @{ FilePath = "powershell.exe"; ArgumentList = $argList; PassThru = $true }
  if ($env:OS -eq "Windows_NT") { $sp.WindowStyle = "Hidden" }
  $timedOut = $false
  try {
    $p = Start-Process @sp
    $null = $p.Handle
    $timedOut = -not $p.WaitForExit($timeoutMin * 60 * 1000)
    if ($timedOut) {
      Log "시간 초과, 강제 종료: $id"
      taskkill /PID $p.Id /T /F 2>&1 | Out-Null
      Start-Sleep -Seconds 2
    }
    $code = if ($timedOut) { 124 } else { [int]$p.ExitCode }
  } catch {
    Log "실행기를 띄우지 못함: $($_.Exception.Message)"
    Add-Content -Path $outFile -Value "[worker] 실행기를 띄우지 못함: $($_.Exception.Message)" -Encoding UTF8
    $code = 1
  }
  $finished = Get-Date
  $ok = ($code -eq 0)
  $statusText = if ($timedOut) { "시간초과" } elseif ($ok) { "성공" } else { "실패" }

  $output = if (Test-Path $outFile) { Get-Content -Path $outFile -Raw -Encoding UTF8 } else { "" }
  if ($null -eq $output) { $output = "" }
  $max = 200000
  if ($output.Length -gt $max) { $output = "(앞부분 " + ($output.Length - $max) + "자 생략)`n" + $output.Substring($output.Length - $max) }

  $retries = if ($t.retries) { [int]$t.retries } else { 0 }
  $maxRetries = if ($null -ne $t.max_retries) { [int]$t.max_retries } else { 1 }
  $requeue = (-not $ok) -and ($retries -lt $maxRetries)

  # 결과 보고서 위치: 성공 → done/, 최종 실패 → failed/, 재시도 예정 → failed/<id>-try<n>.md (기록만 남기고 작업은 큐로)
  $resultRel = if ($ok) { "agents/tasks/done/$id.md" } elseif ($requeue) { "agents/tasks/failed/$id-try$($retries + 1).md" } else { "agents/tasks/failed/$id.md" }
  $md = @(
    "# $title",
    "",
    "- 작업 ID: $id",
    "- 상태: $statusText (종료 코드 $code)",
    "- 실행 PC: $Me",
    "- 시작: $($started.ToString('yyyy-MM-dd HH:mm:ss'))  끝: $($finished.ToString('yyyy-MM-dd HH:mm:ss'))  소요: $([int]($finished - $started).TotalMinutes)분",
    "- 시도: $($retries + 1) / $($maxRetries + 1)$(if ($requeue) { ' → 큐로 되돌려 재시도' })",
    "",
    "## 출력",
    "",
    '```text',
    $output.TrimEnd(),
    '```'
  ) -join "`n"

  Set-Field $t "finished_at" (Now)
  Set-Field $t "exit_code"   $code
  if ($ok) {
    Set-Field $t "status" "done"
    $destDir = "done"
  } elseif ($requeue) {
    Set-Field $t "status"      "queued"
    Set-Field $t "retries"     ($retries + 1)
    Set-Field $t "retry_after" ((Get-Date).AddMinutes(10).ToString("yyyy-MM-ddTHH:mm:sszzz"))
    Set-Field $t "last_error"  "$statusText on $Me (exit $code)"
    $destDir = "queue"
  } else {
    Set-Field $t "status" "failed"
    $destDir = "failed"
  }
  Set-Field $t "result_file" $resultRel
  $destJson = Join-Path (Join-Path $TasksDir $destDir) (Split-Path $Path -Leaf)
  git mv -f $Path $destJson 2>&1 | Out-Null
  Write-Json $destJson $t
  [System.IO.File]::WriteAllText((Join-Path $Repo $resultRel), $md, $utf8)

  Log "실행 끝: $id → $statusText"
  if (-not (Push-Repo ("agent: {0} {1} — {2}" -f $id, $statusText, $Me))) {
    Log "결과 push 실패. 다음 회차에 다시 시도한다 (로컬 커밋은 남아 있음)"
  }
  if ($ok) { Notify "작업 완료: $title" } else { Notify "작업 $statusText`: $title" }
}

function Notify([string]$Text) {
  try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $n = $xml.GetElementsByTagName("text")
    $n.Item(0).AppendChild($xml.CreateTextNode("로빈의밥상 에이전트 ($Me)")) | Out-Null
    $n.Item(1).AppendChild($xml.CreateTextNode($Text)) | Out-Null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Code").Show([Windows.UI.Notifications.ToastNotification]::new($xml))
  } catch {}
}

function Do-Round {
  $n = 0
  while ($n -lt $MaxTasksPerRound) {
    $claim = Claim-Task
    if (-not $claim) { break }
    Run-Task $claim.Path $claim.Task
    $n++
  }
  return $n
}

$mutex = New-Object System.Threading.Mutex($false, "Local\robyn-agent-worker")
if (-not $mutex.WaitOne(0)) { Write-Host "worker 가 이미 실행 중입니다."; exit 0 }
try {
  Log "worker 시작 (Loop=$Loop, 간격=${IntervalSec}s, 브랜치=$Branch)"
  do {
    $ran = Do-Round
    if ($Loop -and $ran -eq 0) {
      # IntervalSec 동안 대기. 중간에 poke 파일이 생기면 바로 깬다.
      $slept = 0
      while ($slept -lt $IntervalSec) {
        if (Test-Path $PokeFile) { Remove-Item $PokeFile -Force -ErrorAction SilentlyContinue; break }
        Start-Sleep -Seconds 10
        $slept += 10
      }
    }
  } while ($Loop)
  Log "worker 종료"
} finally {
  $mutex.ReleaseMutex() | Out-Null
}
