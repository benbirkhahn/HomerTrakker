This branch backs up the Python source currently running on Ben's Mac as of October 6, 2026. It is a disaster-recovery code baseline, not a deployment, merge or claim that the new matching fix is live.

The local and remote starting commit were `5362ead1fff266c162241315aacf188b381fa062`. The snapshot includes 65 current source/docs files from the dirty working directory, including previously untracked launcher, clip matcher, queue monitor and performance/analytics helpers. Exact live/backup hashes are in `recovery/evidence/source-snapshot.json`. Python/shell/JavaScript source is unchanged; prose phone literals and Docker config values are sanitized, and the backup tree's ignore rules are strengthened. No live files, Git index, scheduler, workflows, credentials or queues were changed to create this backup.

The running architecture is:

```text
launchd, every 60 seconds
  scripts/run_homer_poller_once.sh
    homer_minute_poller.py
      statcast_enricher.py
      download_homer_videos.py
      shorts_video_compiler.py
      youtube_queue_monitor.py --apply
      uploader_runner.py
        youtube_homer_bot.py
```

The launcher resolves a Python environment, loads `.homer.env`, acquires a local process lock and locates FFmpeg. It runs Python directly. No n8n process/HTTP dependency occurs in the scheduled Python chain. `N8N_RUNNER` is only an optional noninteractive flag in the uploader. This supports operation while n8n is off; it does not establish an exact historical uptime timeline.

The captured environment used Python 3.13.2, with installed Google/requests dependency versions pinned in `requirements-runtime.lock.txt`. FFmpeg/FFprobe versions and optional n8n version are recorded in `recovery/evidence/runtime-inventory.json`. The dashboard requirements are optional, in `requirements-monitor.txt`; dashboards and historical Twitter/Docker paths are not required for the scheduled YouTube pipeline and were not validated as live services.

The active native n8n workflow structure is included as `recovery/n8n/Fixed_Workflow.reference.sanitized.json`. It is inactive, every node is disabled, credential bindings and execution/pinned/static data are absent. It is a reference only: its Docker-style paths and direct download/upload branches have not been repaired or activated. Historical workflow JSON/execution dumps and databases are excluded; the existing GitHub main/history retains previously published definitions. Do not run/import/activate the reference as a recovery step.

The baseline still contains the known same-player multiple-HR clip/stat mismatch. The new event-identity/animation-manifest fix was developed in a separate isolated copy and passed 55 tests; it remains undeployed and is not silently mixed into this snapshot. Applying that fix requires its separate activation review.

To restore code without publishing:

1. Clone this backup branch into a new directory. Keep old machines/workflows stopped or paused while reviewing recovery; do not create a second publisher.
2. Install a compatible Python 3.13 interpreter and FFmpeg/FFprobe. Run `zsh recovery/prepare_restore.sh --offline` to create a project-local `twitter_bot_env` and a paused `.homer.env`. This does not load launchd, run n8n, authenticate or upload. The launcher already checks the project-local environment first.
3. Run `twitter_bot_env/bin/python3 -m unittest discover -s tests -v`. These checks parse source, verify snapshot hashes, replay a synthetic single-event matcher/enrichment case, and confirm a paused poller exits before state/network/pipeline actions. They use a simulated home directory and block HTTP/process side effects; they are not live acceptance tests.
4. With package access available, `zsh recovery/prepare_restore.sh --install-dependencies` installs the captured runtime dependency lock. No fresh package installation or live media rendering was tested during this backup. Restore your secure private inputs below before attempting continuity of scheduling/upload. Restore remains paused by default.
5. Review the launchd template in `recovery/templates/`, replace `__APP_ROOT__` with the new checkout path, and verify interpreter/media tools. The template does not run on load. Do not load it until credentials, dedupe/scheduling state and YouTube reconciliation are complete and activation is explicitly approved.

A code clone alone cannot preserve dedupe, reserved upload slots, pending media or authentication. Those are deliberately excluded from this public repository. The separate secure backup needs:

| Private input | Recovery purpose |
| --- | --- |
| Actual `.homer.env` | Private configuration, notification endpoints and account/runtime settings; selected numeric/boolean nonsecret settings are separately recorded here. |
| `config/youtube_credentials.json`, `youtube_token.json` | Existing OAuth client/user authorization for the intended account. Do not commit these, use historic exposed values or change scopes/credentials as part of this backup. Rotation status of historically exposed credentials remains unknown. |
| `~/.homer/` | Seen-play state, upload-once ledger, YouTube queue and monitor state. Restore these consistently before considering resumed publication. |
| `MLB_HomeRun_Posts/`, pending `Shorts_Ready/` or `YouTube_Shorts_Ready/`, thumbnails if needed | Pending posts/stats/media and compiled output; not uploaded to GitHub. Already scheduled YouTube videos remain on YouTube. |
| `~/.n8n/` only if recovering the optional n8n service | A consistent database backup plus its matching encryption configuration/key, using secure storage. A workflow JSON export cannot replace credentials or execution state. |

Keep private inputs in encrypted storage you control, separately from public source. No private archive, new repository, paid backup service, credential rotation or host backup subscription was created by this task. If private state is lost, do not start with empty ledgers and assume uploading is safe: reconcile existing YouTube videos/schedules and reconstruct or review dedupe state first. The offline tests cannot prove recovery of authentication, quota, schedules or existing pending uploads.

The new `.gitignore` excludes credentials, runtime JSON/state, databases, environments, logs and media, but ignore rules do not remove secrets already in Git history. The proposed new tree and added/modified diff were scanned for known credential signatures and forbidden private paths, with values suppressed. Existing repository history was not rewritten or force-pushed, and its historical credential exposure was not remedied by this backup.

Verification evidence is in `recovery/evidence/`: source hashes, runtime/dependency inventory, sanitized settings, scan results and a clean-checkout offline restore test transcript. The backup commit is published only on the dedicated branch; main and the currently running checkout are unchanged.
