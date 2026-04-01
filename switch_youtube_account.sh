#!/bin/bash
# Switch YouTube account for the bot by deleting the saved OAuth token
# and launching the auth flow again.

set -euo pipefail

cd "$(dirname "$0")"

TOKEN_FILE="youtube_token.json"
if [ -f "$TOKEN_FILE" ]; then
  echo "🧹 Removing existing OAuth token ($TOKEN_FILE) to force re-auth..."
  rm -f "$TOKEN_FILE"
else
  echo "ℹ️ No existing token found. Proceeding to auth."
fi

echo "🚀 Starting YouTube bot to trigger Google sign-in..."
source twitter_bot_env/bin/activate
python3 youtube_homer_bot.py
