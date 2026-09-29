@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
echo 예시 자료로 전체 흐름을 실행합니다. 실제 자료는 건드리지 않습니다.
%PY% -m robin_workbench.cli example
if errorlevel 1 ( pause & exit /b 1 )
start "" "%USERPROFILE%\Downloads\로빈_요리공구작업실2_결과\예시"
pause
