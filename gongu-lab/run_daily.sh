#!/usr/bin/env bash
# macOS / Linux 용. 매일 아침 예약 실행: 오늘·내일 올릴 콘텐츠를 만들어 두고 오늘 할 일을 알려준다.
set -euo pipefail
cd "$(dirname "$0")/.."

LOG_DIR="gongu-lab/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_$(date +%Y-%m-%d_%H%M).log"

{
  echo "== $(date) 시작"
  git pull --ff-only || echo "[warn] git pull 실패, 로컬 상태로 진행"
  python3 gongu-lab/plan_calendar.py plan || echo "[warn] 캘린더 생성에서 빠진 정보가 있음"

  claude -p "gongu-lab 스킬(.claude/skills/gongu-lab/SKILL.md)의 모드 B 를 수행해라. 먼저 plan_calendar.py today 를 실행하고, 오늘과 내일 항목 중 미작성인 것을 brief 로 지시서를 받아 guidelines.md 와 analysis/ 의 최신 분석을 따라 작성해라. 작성한 파일은 lint_content.py 오류 0건이 될 때까지 고쳐라. 제품 정보(가격·수량·단점·마감)가 schedule.json 에 없으면 지어내지 말고 그 항목을 건너뛰고 무엇이 필요한지 마지막에 적어라. 끝나면 gongu-lab 을 커밋·푸시하고, 마지막에 오늘 올릴 것 목록과 파일 경로, 필요한 정보 목록을 출력해라." \
    --permission-mode acceptEdits \
    --allowedTools "Read,Write,Edit,Glob,Grep,Agent,Bash(python3 *),Bash(git *)" \
    --output-format text

  echo "== $(date) 끝"
} 2>&1 | tee "$LOG"

if command -v osascript >/dev/null 2>&1; then
  osascript -e 'display notification "오늘 올릴 공구 콘텐츠가 준비됐습니다" with title "로빈의밥상 gongu-lab"' || true
fi
