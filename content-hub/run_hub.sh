#!/bin/bash
# 맥/리눅스: crontab -e 에  */15 * * * * /경로/content-hub/run_hub.sh  추가
cd "$(dirname "$0")/.." || exit 1
mkdir -p content-hub/logs
{ echo "== $(date)"; python3 content-hub/hub.py run 2>&1; } >> "content-hub/logs/run_$(date +%F).log"
