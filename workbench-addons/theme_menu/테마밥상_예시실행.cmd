@echo off
chcp 65001 >nul
cd /d "%~dp0"
python theme_menu.py --menus 예시_메뉴후보.csv --birth 1966-09-10 --mbti ISFJ
if errorlevel 1 (
  echo.
  echo 실행에 실패했습니다. 위 [멈춤] 문구의 해결 방법을 확인하세요.
  echo 파이썬이 없다는 오류면 python.org 에서 설치 후 다시 실행하세요.
  pause
  exit /b 1
)
start "" "%USERPROFILE%\Downloads\로빈_테마밥상추천"
pause
