#!/bin/zsh
# Install cron entries for Homer poller (runs every minute)
# and a nightly cleanup to prune temp and old artifacts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POLLER="$SCRIPT_DIR/homer_minute_poller.py"
RUNNER="$SCRIPT_DIR/scripts/run_homer_poller_once.sh"
LOG="$SCRIPT_DIR/logs/homer_poller.log"

if [ ! -f "$POLLER" ]; then
  echo "Poller not found: $POLLER" >&2
  exit 1
fi
if [ ! -f "$RUNNER" ]; then
  echo "Poller runner not found: $RUNNER" >&2
  exit 1
fi

mkdir -p "$SCRIPT_DIR/logs"
chmod +x "$RUNNER"

# Compose crontab additions
CRON_TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v "homer_minute_poller.py" | grep -v "homer_nightly_cleanup" > "$CRON_TMP" || true

# Every minute poller. The runner handles env defaults, locking, and cwd.
echo "* * * * * /bin/zsh \"$RUNNER\" >> \"$LOG\" 2>&1" >> "$CRON_TMP"

# Nightly cleanup at 03:30: remove temp dirs, old compiled videos, and stale source clips
cat >> "$CRON_TMP" <<'EOF'
30 3 * * * /bin/zsh -lc 'find "$HOME/HomerTrakker/Shorts_Ready" -type f -name "*.mp4" -mtime +7 -delete 2>/dev/null; rm -rf "$HOME/HomerTrakker/Shorts_Ready/temp" 2>/dev/null; for d in "$HOME/HomerTrakker/MLB_HomeRun_Posts"/*/videos; do [ -d "$d" ] && find "$d" -type f -name "*.mp4" -mtime +2 -delete 2>/dev/null; done; python3 "$HOME/HomerTrakker/cleanup_media.py" "$(date +\%F -v-1d)" --delete-posts 2>/dev/null || true; python3 -c "from youtube_homer_bot import YouTubeHomeRunBot; YouTubeHomeRunBot()._prune_queue()" 2>/dev/null || true' # homer_nightly_cleanup
EOF

crontab "$CRON_TMP"
rm -f "$CRON_TMP"

echo "✅ Cron installed:"
crontab -l | sed -n '1,10p'
