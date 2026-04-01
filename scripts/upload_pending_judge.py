#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
Upload Pending Aaron Judge Homers (one-shot)
Uploads only the remaining Judge clips that are already compiled.
Uses minimal YouTube scope to avoid re-auth.
"""
import os
from pathlib import Path
from youtube_homer_bot import YouTubeHomeRunBot

# Ensure minimal scope
os.environ.setdefault('HOMER_YT_MINIMAL_SCOPES', '1')

BASE = Path('/Users/benbirkhahn/HomerTrakker')

# Remaining Judge homers to upload (date, gamePk-atBatIndex)
PENDING = [
    ("2025-09-09", "776398-5"),
    ("2025-09-11", "776368-4"),
    ("2025-09-11", "776368-22"),
    ("2025-09-14", "776330-40"),
    ("2025-09-20", "776257-19"),
    ("2025-09-24", "776199-19"),
    ("2025-09-24", "776199-67"),
]

def main():
    bot = YouTubeHomeRunBot()
    if not hasattr(bot, 'youtube') or not bot.youtube:
        print('YouTube service not available; will try next run.')
        return 2

    posted = 0
    skipped = 0
    for d, hid in PENDING:
        vid = BASE / f'Shorts_Ready/Homer_{hid}_{d}_SHORT.mp4'
        if not vid.exists():
            # Skip if the compiled short is not present
            continue
        res = bot.upload_homer_video(hid, d)
        if res and res.get('success') and not res.get('skipped'):
            posted += 1
        elif res and res.get('skipped'):
            skipped += 1
    print(f"Uploaded: {posted}, Skipped(existing): {skipped}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
