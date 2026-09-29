@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% -m robin_workbench.app
if errorlevel 1 (
  echo.
  echo 작업실을 열지 못했습니다.
  echo 파이썬이 없다는 문구가 보이면 python.org 에서 설치할 때 "Add python.exe to PATH"를 체크하세요.
  pause
)
