# HomerTrakker — Quick Start (Operations)

Paths
- Project: /Users/benbirkhahn/HomerTrakker
- Status script: scripts/homer_status_v2.sh
- Control script: scripts/homerctl.sh
- Runtime config: .homer.env
- Logs: logs/homer_poller.log, logs/posted.log
- n8n workflow (import): docs/n8n_homertrakker_minute_poller.json

Daily use
- Check status
  ./scripts/homer_status_v2.sh

- Tail logs (live)
  ./scripts/homerctl.sh tail

- Restart poller (keeps require-both ON by default)
  ./scripts/homerctl.sh restart

- Start/Stop
  ./scripts/homerctl.sh start
  ./scripts/homerctl.sh stop

Runtime config (.homer.env)
- Edit values, then restart via ./scripts/homerctl.sh restart
  HOMER_PAUSE=0
  HOMER_AUTO_UPLOAD=1
  HOMER_BROADCAST_MAX_SECS=15
  HOMER_TOTAL_MAX_SECS=30
  HOMER_REQUIRE_BOTH=1     # keep both angles required
  HOMER_NOTIFY_PHONE=<YOUR_PHONE_NUMBER>
  HOMER_YT_PUBLISH_MODE=scheduled
  HOMER_YT_PUBLISH_START_DELAY_MINUTES=15
  HOMER_YT_PUBLISH_GAP_MINUTES=90
  HOMER_YT_PUBLISH_WINDOW_START_HOUR=16
  HOMER_YT_PUBLISH_WINDOW_END_HOUR=24
  HOMER_YT_CATCHUP_QUEUE_THRESHOLD=16
  HOMER_YT_NORMAL_WINDOW_START_HOUR=16
  HOMER_YT_NORMAL_WINDOW_END_HOUR=24
  HOMER_YT_MAX_PUBLISHES_PER_DAY=4
  HOMER_YT_MAX_QUEUE_ITEMS=8
  HOMER_YT_MAX_HORIZON_DAYS=2
  HOMER_YT_MIN_SCORE=0
  HOMER_YT_BACKLOG_MIN_SCORE=100
  HOMER_YT_DEFER_WEAK_BACKLOG=1
  HOMER_YT_SUPPRESSION_GUARD=1
  HOMER_YT_SUPPRESSION_SLOW_GAP_MINUTES=90
  HOMER_YT_SUPPRESSION_SLOW_MAX_PER_DAY=4
  HOMER_YT_OPTIMIZE_INTERVAL_MINUTES=30
  HOMER_YT_RESCHEDULE_MIN_LEAD_MINUTES=10
  HOMER_YT_QUOTA_BACKOFF_HOURS=6
  HOMER_YT_STABLE_SKIP_MINUTES=120
  HOMER_YT_PERFORMANCE_SYNC_MAX_AGE_MINUTES=180
  HOMER_YT_QUOTA_RECOVERY_STABLE_MINUTES=120

- Refresh performance summary for queue ranking
  python3 youtube_performance_sync.py

- Optional deeper analytics refresh after YouTube Analytics OAuth
  python3 youtube_analytics_sync.py

- Preview/apply score-based optimization for already scheduled private YouTube posts
  python3 optimize_youtube_queue.py
  python3 optimize_youtube_queue.py --apply

- Run automation-style throttled queue maintenance
  python3 youtube_queue_monitor.py --apply

- Preview/apply tighter times without changing score order
  python3 reschedule_youtube_posts.py
  python3 reschedule_youtube_posts.py --apply

n8n (optional)
- Import docs/n8n_homertrakker_minute_poller.json into n8n (Workflows → Import from File)
- Update the Execute Command node if needed
- Important: stop the background loop first to avoid duplicates
  ./scripts/homerctl.sh stop
  Then activate the n8n workflow

Troubleshooting
- iMessage prompt: If detection/upload alerts don’t arrive, open Messages once and allow Terminal automation when prompted.
- One instance only: Use ./scripts/homerctl.sh status to ensure only one poller loop is running.
- ffmpeg present: ffmpeg/ffprobe 8.0 already installed and on PATH; if you move machines, install via brew install ffmpeg.
- YouTube OAuth: Token lives at youtube_token.json; if auth expires, the uploader will re-prompt automatically.
