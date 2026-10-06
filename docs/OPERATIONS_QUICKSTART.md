# Operations Quick Start (Daily Run + Optional Autostart)

This is a quick reference for starting, monitoring, and (optionally) auto-starting the HomerTrakker pipeline.

The current codebase is configured to:
- Detect live HRs and generate posts
- Backfill both angles (4000K broadcast + animated) when available
- Enrich Statcast before compile/upload so titles/descriptions include distance, LA, and EV
- Compile only when both angles are present (automation default), then build Shorts (15s broadcast / 30s total), upload, and clean up sources

## Daily manual start (if not already running)

1) Start the background poller (with auto-upload)

   ```bash
   nohup /bin/zsh -lc 'export HOMER_PAUSE=0 HOMER_AUTO_UPLOAD=1 HOMER_BROADCAST_MAX_SECS=15 HOMER_TOTAL_MAX_SECS=30 HOMER_REQUIRE_BOTH=1; while true; do ~/twitter_bot_env/bin/python3 ~/HomerTrakker/homer_minute_poller.py || true; sleep 60; done' > ~/HomerTrakker/logs/homer_poller.log 2>&1 & echo $!
   ```

2) Keep the Mac awake during games (optional but recommended)

   ```bash
   caffeinate -dimsu
   ```

3) Check status

   ```bash
   pgrep -f "HomerTrakker/homer_minute_poller.py"
   tail -n 80 ~/HomerTrakker/logs/homer_poller.log
   ```

4) Stop / Pause / Resume

   ```bash
   # Stop all pollers
   pkill -f "HomerTrakker/homer_minute_poller.py"

   # Pause without stopping
   touch /tmp/homer_pause

   # Resume
   rm -f /tmp/homer_pause
   ```

## Optional: Persistent autostart via cron (do later if desired)

- Install cron entries (every minute poller + nightly cleanup at 03:30):

  ```bash
  cd ~/HomerTrakker && ./install_homer_cron.sh
  ```

- Verify:

  ```bash
  crontab -l | sed -n '1,20p'
  ```

- Remove cron entries later (example, keeps everything except our entries):

  ```bash
  (crontab -l | grep -v "homer_minute_poller.py" | grep -v "homer_nightly_cleanup") | crontab -
  ```

## One-off reprocess for a specific homer

1) Ensure the post file exists in MLB_HomeRun_Posts/DATE (restore if archived)
2) Download both angles (policy prefers 4000K + animated):

   ```bash
   python3 download_homer_videos.py YYYY-MM-DD
   ```

3) Compile with duration caps:

   ```bash
   HOMER_REQUIRE_BOTH=1 HOMER_BROADCAST_MAX_SECS=15 HOMER_TOTAL_MAX_SECS=30 \
   python3 shorts_video_compiler.py YYYY-MM-DD
   ```

4) Clear the upload-once ledger key (DATE:NUM) from ~/.homer/uploads.json
5) Upload just that homer (non-interactive):

   ```bash
   python3 - <<'PY'
   from youtube_homer_bot import YouTubeHomeRunBot as B
   b = B()
   b.upload_homer_video(4, "YYYY-MM-DD")  # change homer number
   PY
   ```

## Troubleshooting tips

- If uploads fail with an auth/refresh error, run youtube_homer_bot.py once interactively and approve Google OAuth. Token is saved to youtube_token.json.
- If a compiled upload is missing an angle, MLB may not have published it yet. The poller will backfill when it appears; by default the system won’t re-upload a video that’s already been posted (upload-once ledger). Ask if you want a hold-off/wait-for-both policy.
