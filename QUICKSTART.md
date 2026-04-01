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
  HOMER_NOTIFY_PHONE=+19144142424

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
