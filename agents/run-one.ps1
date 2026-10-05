<#
agents/run-one.ps1 — 작업 하나를 실제로 실행하는 작은 실행기. worker.ps1 이 별도 프로세스로 띄운다 (시간 제한·강제 종료용).
  - prompt 가 있으면: 프롬프트를 표준입력으로 claude -p 에 넘긴다. agent 가 "codex" 면 codex exec 에 넘긴다.
  - command 가 있으면: 그 PowerShell 명령을 그대로 실행한다.
  출력은 -OutFile 에 UTF-8 로 저장하고, 종료 코드를 그대로 돌려준다.
#>
param(
  [Parameter(Mandatory = $true)][string]$TaskFile,
  [Parameter(Mandatory = $true)][string]$OutFile
)
$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
[Console]::InputEncoding  = $utf8
$OutputEncoding = $utf8

$t    = Get-Content -Path $TaskFile -Raw -Encoding UTF8 | ConvertFrom-Json
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$cwd  = if ($t.cwd) { Join-Path $repo $t.cwd } else { $repo }
Set-Location $cwd

$code = 0
try {
  if ($t.command) {
    & ([scriptblock]::Create($t.command)) 2>&1 | Out-File -FilePath $OutFile -Encoding UTF8
    if ($LASTEXITCODE) { $code = [int]$LASTEXITCODE }
  } elseif ($t.agent -eq "codex") {
    $sandbox = if ($t.sandbox) { [string]$t.sandbox } else { "workspace-write" }
    [string]$t.prompt | codex exec --sandbox $sandbox - 2>&1 |
      Out-File -FilePath $OutFile -Encoding UTF8
    $code = [int]$LASTEXITCODE
  } else {
    $tools = if ($t.allowed_tools)   { [string]$t.allowed_tools }   else { "Read,Glob,Grep" }
    $mode  = if ($t.permission_mode) { [string]$t.permission_mode } else { "acceptEdits" }
    [string]$t.prompt | claude -p --permission-mode $mode --allowedTools $tools --output-format text 2>&1 |
      Out-File -FilePath $OutFile -Encoding UTF8
    $code = [int]$LASTEXITCODE
  }
} catch {
  "[run-one] 오류: $($_.Exception.Message)" | Out-File -FilePath $OutFile -Encoding UTF8 -Append
  $code = 1
}
exit $code
