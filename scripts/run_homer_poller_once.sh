#!/bin/zsh
# Run one locked HomerTrakker poller pass for cron/launch wrappers.

set -u

BASE_DIR="${0:A:h}/.."
ENV_FILE="$BASE_DIR/.homer.env"
LOCK_DIR="/tmp/homer_minute_poller.lock"

resolve_python(){
  if [[ -x "$BASE_DIR/twitter_bot_env/bin/python3" ]]; then
    print -r -- "$BASE_DIR/twitter_bot_env/bin/python3"
  elif [[ -x "$HOME/twitter_bot_env/bin/python3" ]]; then
    print -r -- "$HOME/twitter_bot_env/bin/python3"
  elif [[ -x "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" ]]; then
    print -r -- "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  else
    command -v python3
  fi
}

acquire_lock(){
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    print -r -- "$$" > "$LOCK_DIR/pid"
    return 0
  fi

  # A forced shutdown can leave the old directory-only lock behind.  The
  # current format records the runner PID, so stale locks can be recovered
  # without blocking every later cron tick.
  local lock_pid=""
  [[ -f "$LOCK_DIR/pid" ]] && lock_pid=$(<"$LOCK_DIR/pid")
  if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
    return 1
  fi
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || return 1
  mkdir "$LOCK_DIR" || return 1
  print -r -- "$$" > "$LOCK_DIR/pid"
}

if ! acquire_lock; then
  echo "Poller already running; skipping this tick."
  exit 0
fi
trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$BASE_DIR" || exit 1

# Background jobs started by launchd/nohup do not reliably inherit the
# interactive shell's Homebrew path on Apple Silicon.  The video pipeline
# invokes ffmpeg/ffprobe by name, so make their standard locations explicit
# before starting Python.
for media_bin in /opt/homebrew/bin /usr/local/bin; do
  if [[ -d "$media_bin" ]]; then
    case ":$PATH:" in
      *":$media_bin:"*) ;;
      *) export PATH="$media_bin:$PATH" ;;
    esac
  fi
done

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "Media tools unavailable: install ffmpeg and ensure it is on PATH."
  exit 1
fi

set -a
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
set +a

export HOMER_PAUSE="${HOMER_PAUSE:-0}"
export HOMER_AUTO_UPLOAD="${HOMER_AUTO_UPLOAD:-1}"
export HOMER_NONINTERACTIVE=1
export PYTHONUNBUFFERED=1
export HOMER_BROADCAST_MAX_SECS="${HOMER_BROADCAST_MAX_SECS:-15}"
export HOMER_TOTAL_MAX_SECS="${HOMER_TOTAL_MAX_SECS:-30}"
export HOMER_REQUIRE_BOTH="${HOMER_REQUIRE_BOTH:-1}"

"$(resolve_python)" "$BASE_DIR/homer_minute_poller.py"
