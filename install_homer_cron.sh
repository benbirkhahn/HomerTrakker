#!/bin/zsh
# Install cron entries for Homer poller (runs every minute)
# and a nightly cleanup to prune temp and old artifacts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_ACTIVATE="$HOME/twitter_bot_env/bin/activate"
POLLER="$SCRIPT_DIR/homer_minute_poller.py"

if [ ! -f "$POLLER" ]; then
  echo "Poller not found: $POLLER" >&2
  exit 1
fi

# Compose crontab additions
CRON_TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v "homer_minute_poller.py" | grep -v "homer_nightly_cleanup" > "$CRON_TMP" || true

# Every minute poller
echo "* * * * * /bin/zsh -lc 'source $VENV_ACTIVATE && python3 $POLLER'" >> "$CRON_TMP"

# Nightly cleanup at 03:30: remove temp dirs and leftover compiled videos older than 7 days
cat >> "$CRON_TMP" <<'EOF'
30 3 * * * /bin/zsh -lc 'find "$HOME/HomerTrakker/Shorts_Ready" -type f -name "*.mp4" -mtime +7 -delete 2>/dev/null; rm -rf "$HOME/HomerTrakker/Shorts_Ready/temp" 2>/dev/null; python3 "$HOME/HomerTrakker/cleanup_media.py" "$(date +\%F -v-1d)" --delete-posts 2>/dev/null || true' # homer_nightly_cleanup
EOF

crontab "$CRON_TMP"
rm -f "$CRON_TMP"

echo "✅ Cron installed:"
crontab -l | sed -n '1,10p'
