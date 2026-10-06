#!/usr/bin/env python3
"""
Non-interactive YouTube uploader runner.
Invoked by the minute poller to upload all compiled Shorts for a given date.
Respects the upload-once ledger configured in youtube_homer_bot.py.
"""
import subprocess
import sys
from pathlib import Path

def main():
    from statcast_enricher import StatcastEnricher
    from youtube_homer_bot import YouTubeHomeRunBot
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    # Ensure statcast JSON exists for richer metadata
    try:
        se = StatcastEnricher(date_arg)
        se.enrich_all()
    except Exception as e:
        print(f"⚠️  Statcast enricher failed (continuing): {e}")
    try:
        import youtube_queue_monitor
        youtube_queue_monitor.main(["--apply"])
    except Exception as e:
        print(f"⚠️  YouTube queue monitor failed (continuing): {e}")
    bot = YouTubeHomeRunBot()
    # If auth failed (e.g., missing credentials), abort cleanly
    if not hasattr(bot, 'youtube') or not bot.youtube:
        print("❌ YouTube service not available; aborting upload")
        print(f"🔐 Re-authenticate with: python3 {Path(__file__).resolve().with_name('youtube_homer_bot.py')} --reauth")
        sys.exit(2)
    bot.upload_all_homers(date_arg)

if __name__ == "__main__":
    main()
