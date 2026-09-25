#!/usr/bin/env bash
# macOS / Linux 용. 저장소 폴더에서 실행하거나 예약 작업(launchd, cron)에 등록한다.
# 하는 일: 최신 코드 받기 → Claude Code 에 threads-watch 스킬 실행 지시 → 보고서 커밋·푸시
set -euo pipefail
cd "$(dirname "$0")/.."

LOG_DIR="threads-watch/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d_%H%M).log"

{
  echo "== $(date) 시작"
  git pull --ff-only || echo "[warn] git pull 실패, 로컬 상태로 진행"

  claude -p "threads-watch 스킬(.claude/skills/threads-watch/SKILL.md)의 실행 순서를 1번부터 6번까지 그대로 수행해라. 새 글이 없으면 한 줄만 남기고 끝내라. 새 글이 있으면 보고서를 threads-watch/reports/ 에 저장하고 커밋·푸시까지 마쳐라. 마지막에 차용 판정 요약 표와 1순위 적용안 전문을 출력해라." \
    --permission-mode acceptEdits \
    --allowedTools "Read,Write,Edit,Glob,Grep,WebFetch,Bash(python3 *),Bash(git *)" \
    --output-format text

  echo "== $(date) 끝"
} 2>&1 | tee "$LOG"

# 보고서 마지막 부분을 알림으로 (macOS 만). 다른 OS 는 무시된다.
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'display notification "스레드 레퍼런스 보고서가 준비됐습니다" with title "로빈의밥상 threads-watch"' || true
fi
