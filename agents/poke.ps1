<#
agents/poke.ps1 — (2단계) 중앙 PC 에서 특정 PC 의 상주 worker 를 즉시 깨운다. PowerShell Remoting 이 켜져 있어야 한다 (README 2단계).
  powershell -ExecutionPolicy Bypass -File agents\poke.ps1 -Pc PC-EDIT
안 되면 그냥 기다리면 된다. worker 는 IntervalSec(기본 5분)마다 큐를 본다.
#>
param([Parameter(Mandatory = $true)][string]$Pc)
$ErrorActionPreference = "Stop"
$roster = Get-Content -Path (Join-Path $PSScriptRoot "agents.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$w = @($roster.workers + $roster.central) | Where-Object { $_.name -eq $Pc } | Select-Object -First 1
if (-not $w -or -not $w.repo_path) { throw "agents.json 에 $Pc 의 repo_path 가 없습니다." }
Invoke-Command -ComputerName $Pc -ScriptBlock {
  param($repoPath)
  $dir = Join-Path $repoPath "agents\logs"
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  New-Item -ItemType File -Force -Path (Join-Path $dir "poke") | Out-Null
} -ArgumentList $w.repo_path
Write-Host "$Pc 의 worker 를 깨웠습니다."
