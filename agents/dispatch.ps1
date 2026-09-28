<#
agents/dispatch.ps1 — 중앙 PC 에서 작업을 큐에 넣는다. 작업 파일(JSON)을 agents/tasks/queue 에 만들고 커밋·푸시한다.

  예) 스레드 분석을 편집 PC 에:
    powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -To PC-EDIT -Title "threads-watch" -PromptFile agents\prompts\threads-watch.txt -AllowedTools "Read,Write,Edit,Glob,Grep,WebFetch,Bash(python *),Bash(git *)"
  예) 아무 PC 나 먼저 노는 PC 에 글쓰기:
    powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -Title "쇼츠 설명글" -Prompt "..."
  예) Claude 없이 파이썬 스크립트만:
    powershell -ExecutionPolicy Bypass -File agents\dispatch.ps1 -To PC-SUB -Title "원본 변환" -Command "python tools\convert.py D:\원본" -TimeoutMin 180
#>
param(
  [string]$Prompt,
  [string]$PromptFile,
  [string]$Command,
  [string]$To = "any",
  [string]$Title = "task",
  [string]$Cwd = ".",
  [string]$AllowedTools = "Read,Write,Edit,Glob,Grep,WebFetch,Bash(python *),Bash(git *)",
  [string]$PermissionMode = "acceptEdits",
  [int]$TimeoutMin = 60,
  [int]$MaxRetries = 1,
  [switch]$NoPush
)
$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo
$Branch = (git rev-parse --abbrev-ref HEAD).Trim()

if ($PromptFile) { $Prompt = Get-Content -Path $PromptFile -Raw -Encoding UTF8 }
if (-not $Prompt -and -not $Command) { throw "-Prompt, -PromptFile, -Command 중 하나는 있어야 합니다." }
if ($Prompt -and $Command) { throw "-Prompt 와 -Command 는 같이 쓸 수 없습니다." }

# PC 명단 확인 (경고만)
$rosterPath = Join-Path $PSScriptRoot "agents.json"
if ($To -ne "any" -and (Test-Path $rosterPath)) {
  $roster = Get-Content -Path $rosterPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $known = @($roster.central.name) + @($roster.workers | ForEach-Object { $_.name })
  if ($known -notcontains $To) { Write-Warning "agents.json 에 없는 PC 이름입니다: $To (그 PC 의 hostname 과 같은지 확인)" }
}

$slug = ($Title -replace '\s+', '-') -replace '[^\p{L}\p{N}_-]', ''
if (-not $slug) { $slug = "task" }
$id = "{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), $slug

$task = [ordered]@{
  id              = $id
  title           = $Title
  to              = $To
  status          = "queued"
  cwd             = $Cwd
  timeout_min     = $TimeoutMin
  max_retries     = $MaxRetries
  retries         = 0
  created_by      = $env:COMPUTERNAME
  created_at      = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
}
if ($Command) {
  $task.command = $Command
} else {
  $task.prompt          = $Prompt.TrimEnd()
  $task.allowed_tools   = $AllowedTools
  $task.permission_mode = $PermissionMode
}

$json = $task | ConvertTo-Json -Depth 8
$json = [regex]::Replace($json, '(?<!\\)((?:\\\\)*)\\u([0-9a-fA-F]{4})', {
  param($m)
  $c = [Convert]::ToInt32($m.Groups[2].Value, 16)
  if ($c -lt 0x20 -or $c -eq 0x22 -or $c -eq 0x5C) { return $m.Value }
  return $m.Groups[1].Value + [string][char]$c
})
$queueDir = Join-Path $Repo "agents\tasks\queue"
New-Item -ItemType Directory -Force -Path $queueDir | Out-Null
$path = Join-Path $queueDir "$id.json"
[System.IO.File]::WriteAllText($path, $json, $utf8)
Write-Host "작업 생성: agents/tasks/queue/$id.json  (대상: $To)"

if ($NoPush) { Write-Host "푸시하지 않음 (-NoPush)."; exit 0 }

$ErrorActionPreference = "Continue"
git pull --rebase --autostash -q origin $Branch 2>&1 | Out-Null
git add -- $path 2>&1 | Out-Null
git commit -q -m ("dispatch: {0} → {1}" -f $id, $To) 2>&1 | Out-Null
for ($i = 1; $i -le 5; $i++) {
  $out = git push origin $Branch 2>&1
  if ($LASTEXITCODE -eq 0) { Write-Host "푸시 완료. worker 가 다음 확인 때 가져갑니다 (즉시 실행: poke.ps1 -Pc $To)."; exit 0 }
  Write-Host "push 실패 ($i/5), 재시도: $out"
  git pull --rebase --autostash -q origin $Branch 2>&1 | Out-Null
  Start-Sleep -Seconds (3 * $i)
}
Write-Error "푸시 실패. 네트워크 확인 후 'git push' 를 직접 실행하세요."
exit 1
