#!/bin/zsh
# homerctl.sh — simple control for HomerTrakker poller
# Usage: ./scripts/homerctl.sh [start|stop|restart|status|tail]

set -euo pipefail

BASE_DIR="${0:A:h}/.."
LOG="$BASE_DIR/logs/homer_poller.log"
ENV_FILE="$BASE_DIR/.homer.env"
RUNNER="$BASE_DIR/scripts/run_homer_poller_once.sh"

ensure_dirs(){
  mkdir -p "$BASE_DIR/logs"
}

load_env(){
  # shellcheck disable=SC1090
  [[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
}

pids(){
  # macOS process arguments preserve the scripts/../ segment used by the
  # runner, so matching the literal path can miss a healthy poller.
  ps -axo pid=,command= | awk '/HomerTrakker\/.*homer_minute_poller\.py/ && !/awk/ {print $1}'
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
  chmod +x "$RUNNER"
  nohup /bin/zsh -lc 'while true; do /bin/zsh "'$RUNNER'" || true; sleep 60; done' > "$LOG" 2>&1 &
  sleep 1
  echo "Started. PIDs: $(pids | tr '\n' ' ')"
}

stop(){
  local p; p=$(pids)
  if [[ -z "$p" ]]; then echo "Poller not running"; return 0; fi
  # A poller can be waiting on a downloader/compiler/uploader.  Stop children
  # first so none are orphaned and left holding the single-instance lock.
  terminate_tree(){
    local parent="$1" child
    for child in $(pgrep -P "$parent" 2>/dev/null || true); do
      terminate_tree "$child"
    done
    kill "$parent" 2>/dev/null || true
  }
  for p in $p; do terminate_tree "$p"; done
  sleep 1
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
