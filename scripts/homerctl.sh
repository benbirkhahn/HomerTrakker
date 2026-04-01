#!/bin/zsh
# homerctl.sh — simple control for HomerTrakker poller
# Usage: ./scripts/homerctl.sh [start|stop|restart|status|tail]

set -euo pipefail

BASE_DIR="${0:A:h}/.."
PY="/Users/benbirkhahn/twitter_bot_env/bin/python3"
LOG="$BASE_DIR/logs/homer_poller.log"
ENV_FILE="$BASE_DIR/.homer.env"

ensure_dirs(){
  mkdir -p "$BASE_DIR/logs"
}

load_env(){
  # shellcheck disable=SC1090
  [[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
}

pids(){
  pgrep -f "HomerTrakker/homer_minute_poller.py" || true
}

start(){
  ensure_dirs; load_env
  if [[ -n "$(pids)" ]]; then
    echo "Poller already running: $(pids | tr '\n' ' ')"; return 0
  fi
  : ${HOMER_PAUSE:=0}
  : ${HOMER_AUTO_UPLOAD:=1}
  : ${HOMER_BROADCAST_MAX_SECS:=15}
  : ${HOMER_TOTAL_MAX_SECS:=30}
  : ${HOMER_REQUIRE_BOTH:=1}
  : ${HOMER_NOTIFY_PHONE:=""}
  nohup /bin/zsh -lc 'export HOMER_PAUSE='$HOMER_PAUSE' HOMER_AUTO_UPLOAD='$HOMER_AUTO_UPLOAD' HOMER_BROADCAST_MAX_SECS='$HOMER_BROADCAST_MAX_SECS' HOMER_TOTAL_MAX_SECS='$HOMER_TOTAL_MAX_SECS' HOMER_REQUIRE_BOTH='$HOMER_REQUIRE_BOTH' HOMER_NOTIFY_PHONE='$HOMER_NOTIFY_PHONE'; while true; do '$PY' '$BASE_DIR'/homer_minute_poller.py || true; sleep 60; done' > "$LOG" 2>&1 &
  sleep 1
  echo "Started. PIDs: $(pids | tr '\n' ' ')"
}

stop(){
  local p; p=$(pids)
  if [[ -z "$p" ]]; then echo "Poller not running"; return 0; fi
  pkill -f "HomerTrakker/homer_minute_poller.py" || true
  echo "Stopped."
}

restart(){ stop; sleep 1; start; }

status(){
  if [[ -n "$(pids)" ]]; then
    echo "Running: $(pids | tr '\n' ' ')"; echo "Log: $LOG"; tail -n 5 "$LOG" || true
  else
    echo "Not running"; echo "Log: $LOG"; [[ -f "$LOG" ]] && tail -n 5 "$LOG" || true
  fi
}

tail_log(){ ensure_dirs; echo "Tailing $LOG (Ctrl-C to stop)"; tail -f "$LOG"; }

cmd=${1:-status}
case "$cmd" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  tail) tail_log ;;
  *) echo "Usage: $0 [start|stop|restart|status|tail]"; exit 1;;
 esac
