#!/bin/zsh
# homer_status_v2.sh — quick health snapshot for HomerTrakker (fixed colors and glob)
# Usage: ./scripts/homer_status_v2.sh

set -euo pipefail

BASE_DIR="${0:A:h}/.."
LOG="$BASE_DIR/logs/homer_poller.log"
POSTS_BASE="$BASE_DIR/MLB_HomeRun_Posts"
TODAY=$(date +%F)

# Colors (ANSI)
B=$'\033[1m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; Z=$'\033[0m'

pid_list=$(pgrep -f "HomerTrakker/homer_minute_poller.py" | tr '\n' ' ' || true)

print_line(){
  printf "%s\n" "$1"
}

print_line "${B}HomerTrakker Status — $(date)${Z}"
print_line "${C}Dir${Z}: $BASE_DIR"
print_line "${C}Today${Z}: $TODAY"

if [[ -n "$pid_list" ]]; then
  print_line "${G}Poller running${Z}: PIDs: $pid_list"
else
  print_line "${R}Poller not running${Z}"
fi

# Window dates (yday + today)
YDAY=$(date -v-1d +%F 2>/dev/null || python3 - <<PY
from datetime import datetime,timedelta
print((datetime.now()-timedelta(days=1)).strftime('%Y-%m-%d'))
PY
)
print_line "${C}Window${Z}: $YDAY → $TODAY"

# Today posts count
POSTS_DIR="$POSTS_BASE/$TODAY"
POST_CT=0
if [[ -d "$POSTS_DIR" ]]; then
  POST_CT=$(find "$POSTS_DIR" -maxdepth 1 -type f -name 'tonights_homer_*.txt' 2>/dev/null | wc -l | tr -d ' ')
fi
print_line "${C}Posts today${Z}: $POST_CT"

# Shorts_Ready count
SHORTS_CT=$(ls -1 "$BASE_DIR/Shorts_Ready"/*.mp4 2>/dev/null | wc -l | tr -d ' ')
print_line "${C}Shorts ready${Z}: $SHORTS_CT"

# Last actions from log
if [[ -f "$LOG" ]]; then
  print_line "${C}Last 10 log lines${Z}:"
  tail -n 10 "$LOG"
else
  print_line "${Y}No poller log yet at $LOG${Z}"
fi

# Require-both flag
REQ=${HOMER_REQUIRE_BOTH:-}
if [[ -z "$REQ" ]]; then
  REQ=$(ps -fp $(pgrep -f "HomerTrakker/homer_minute_poller.py" | head -n1) 2>/dev/null | grep -oE "HOMER_REQUIRE_BOTH=\S+" | cut -d= -f2 || true)
fi
if [[ "$REQ" == "1" ]]; then
  print_line "${G}Require both clips: ON${Z}"
else
  print_line "${Y}Require both clips: OFF${Z}"
fi

# YouTube token presence
if [[ -f "$BASE_DIR/youtube_token.json" ]]; then
  print_line "${G}YouTube auth token: present${Z}"
else
  print_line "${R}YouTube auth token: missing${Z}"
fi
