# Building the HomerTrakker pipeline in n8n (end-to-end guide)

This guide shows how to reproduce your current HomerTrakker automation in n8n. It covers detection, backfilling both angles (4000K broadcast + animated), stat enrichment, compile (requiring both angles), upload to YouTube, iMessage/Twilio notifications, and cleanup.

You can either:
- Orchestrate your existing Python scripts from n8n (recommended; fastest)
- Or build more steps natively with n8n nodes (more work; outlined below)

## Prerequisites

- Self‑hosted n8n running on the same machine that has:
  - Python 3.13 and your working virtualenv with scripts:
    - /Users/benbirkhahn/twitter_bot_env/bin/python3
    - Scripts live in /Users/benbirkhahn/HomerTrakker
  - ffmpeg and ffprobe available on PATH
  - macOS Messages app logged in (for iMessage via osascript), if you want iMessage alerts from n8n
- n8n Credentials set up for:
  - YouTube OAuth2 (scope: youtube.upload)
  - Twilio (optional) for SMS
  - Slack/Discord webhooks (optional)

## High‑level architecture in n8n

Two workflows are sufficient:

1) Minute Poller (runs every 1 minute)
   - Detect HRs during live window
   - Generate posts (and iMessage you at detection)
   - Backfill 4000K broadcast + animated URLs into posts
   - Download videos
   - Compile Shorts (require both angles)
   - Upload to YouTube and iMessage the link
   - Cleanup sources

2) Nightly Cleanup (runs 03:30)
   - Remove compiled videos older than 7 days
   - Clean source videos/stats for yesterday

We’ll rely on your existing Python scripts for the heavy lifting and gate logic. n8n will queue/run them at the right times and handle notifications.

## Data storage (idempotency)

Use one n8n Data Store to track seen HR plays and uploads:
- Name: homer_state
- Keys
  - seen:{gamePk}:{atBatIndex} → true
  - uploaded:{YYYY-MM-DD}:{homerNum} → { videoId, title, at }

This prevents duplicate posts and duplicate uploads.

## Workflow 1: Minute Poller (every minute)

Node list and wiring (recommended orchestrated approach):

1) Cron (Trigger)
   - Every minute

2) Execute Command: Refresh detection/processing
   - Command runs your consolidated Python pipeline steps safely in sequence and is idempotent.
   - The following compound command mirrors your working flow and enforces “require both angles.”
   ```bash path=null start=null
   /bin/zsh -lc '
     export HOMER_PAUSE=0 \
            HOMER_AUTO_UPLOAD=1 \
            HOMER_BROADCAST_MAX_SECS=15 \
            HOMER_TOTAL_MAX_SECS=30 \
            HOMER_REQUIRE_BOTH=1 \
            HOMER_NOTIFY_PHONE=+1XXXXXXXXXX;
     # 0) Detect + generate posts (within live window)
     /Users/benbirkhahn/twitter_bot_env/bin/python3 /Users/benbirkhahn/HomerTrakker/homer_minute_poller.py || true
   '
   ```
   Notes:
   - This uses your existing poller which already:
     - Generates the post (and sends detection iMessage)
     - Backfills both angles into posts
     - Enriches Statcast
     - Downloads clips
     - Compiles with HOMER_REQUIRE_BOTH=1
     - Uploads (non‑interactive) and cleans up
   - In n8n, set “Continue On Fail” for resilience.

That’s it for the orchestrated path; the poller script encapsulates the full pipeline. The remaining sections show how you could build the same logic inside n8n nodes if you want more granular control.

---

## (Alternative) Building the steps natively in n8n

If you prefer to decompose steps inside n8n, here is a blueprint using core nodes. You can mix and match—e.g., detect and backfill with nodes, then call your compiler/uploader via Execute Command.

1) Cron (Trigger)
   - Every minute

2) Function (Compute Dates and Windows)
   - Inputs: none
   - Outputs: JSON with today, yesterday, pre/post windows
   ```javascript path=null start=null
   // Example window: 10 min pregame, 6 hours post
   const now = new Date();
   const fmt = d => d.toISOString().slice(0,10);
   const today = fmt(now);
   const yday = fmt(new Date(now.getTime() - 24*3600*1000));
   return [{ today, yday, preMin: 10, postHours: 6 }];
   ```

3) HTTP Request (Fetch MLB schedule for today)
   - GET https://statsapi.mlb.com/api/v1/schedule
   - Query: sportId=1&date={{$json.today}}&hydrate=team,linescore

4) HTTP Request (Fetch MLB schedule for yesterday)
   - Same endpoint, date={{$json.yday}}

5) Function (Merge and filter active games)
   - Input: the two schedule payloads
   - Output: array of game objects within active window
   ```javascript path=null start=null
   const collect = items => items.flatMap(it => (it.json.dates||[]).flatMap(d => d.games||[]));
   const todayGames = collect($items("HTTP Request", 0));
   const ydayGames  = collect($items("HTTP Request1", 0));
   const games = [...ydayGames, ...todayGames];

   const now = new Date();
   const preMs = 10*60*1000;
   const postMs = 6*3600*1000;
   const within = game => {
     const start = new Date(game.gameDate).getTime();
     const n = now.getTime();
     return (start - preMs) <= n && n <= (start + postMs);
   };

   return games.filter(g => within(g));
   ```

6) Split In Batches (games)

7) HTTP Request (Fetch live feed for gamePk)
   - GET https://statsapi.mlb.com/api/v1.1/game/{{ $json.gamePk }}/feed/live

8) Function (Find HR plays and dedupe)
   - Checks result.eventType === 'home_run'
   - Builds a key `${gamePk}:${about.atBatIndex}` and checks n8n Data Store homer_state (seen:*)
   - Emits new HR plays only; also writes seen:* keys so we don’t process twice
   ```javascript path=null start=null
   // For each game feed, extract unseen HR plays
   const store = await this.getWorkflowStaticData('global'); // or use Data Store node
   const plays = $json.liveData?.plays?.allPlays || [];
   const out = [];
   for (const p of plays) {
     if (p.result?.eventType !== 'home_run') continue;
     const key = `${$json.gamePk}:${p.about?.atBatIndex}`;
     if (store[`seen:${key}`]) continue;
     store[`seen:${key}`] = true;
     out.push({ json: { key, gamePk: $json.gamePk, play: p } });
   }
   return out;
   ```

9) HTTP Request (Fetch MLB content/highlights for gamePk)
   - GET https://statsapi.mlb.com/api/v1/game/{{ $json.gamePk }}/content

10) Function (Select playbacks: 4000K + darkroom, require both)
   - Picks at most one diamond (prefer 4000K) + one darkroom
   - If both unavailable, return empty to skip for now (the next minute will try again)
   ```javascript path=null start=null
   const content = $json; // from HTTP Request
   // find matching highlight items by play’s batter id or name
   const play = $item(0).$node["Function"].json.play; // upstream play
   const batterId = play.matchup?.batter?.id;
   const items = content.highlights?.highlights?.items || [];

   const isHRItem = it => (it.headline||it.title||'').toLowerCase().includes('home run');
   const byBatter = it => (it.keywordsAll||[]).some(k => k.type==='player' && String(k.playerId)===String(batterId));

   const chosen = items.filter(it => isHRItem(it) && (byBatter(it)));
   const urls = [];
   for (const it of chosen) {
     for (const pb of (it.playbacks||[])) {
       const url = pb.url||'';
       if (!url.endsWith('.mp4')) continue;
       urls.push(url);
     }
   }
   // Partition
   const diamond = urls.filter(u => u.includes('mlb-cuts-diamond.mlb.com'));
   const darkroom= urls.filter(u => u.includes('darkroom-clips.mlb.com'));

   // pick single diamond preferring 4000K
   let d = null;
   for (const u of diamond) { if (u.includes('4000K')) { d=u; break; } }
   if (!d && diamond.length) d = diamond[0];
   const a = darkroom[0] || null;

   if (!(d && a)) {
     return []; // require both; backfill will try again next minute
   }
   return [{ json: { d, a, gamePk: $item(0).$node["Function"].json.gamePk, play } }];
   ```

11) Function (Build post text)
   - Creates the text body to match your file format
   ```javascript path=null start=null
   const play = $json.play;
   const batter = play.matchup?.batter?.fullName || 'Unknown Player';
   const pitcher= play.matchup?.pitcher?.fullName || '';
   const inning = `${play.about?.halfInning||''} ${play.about?.inning||''}`.trim();
   const desc   = play.result?.description || '';
   const gamePk = $json.gamePk;
   const lines = [];
   lines.push("TONIGHT'S HOME RUN - READY FOR @homertrakker");
   lines.push("=======================================================\n");
   lines.push("CAPTION:");
   lines.push("🏠⚾ HOME RUN ALERT! ⚾🏠");
   lines.push(`🔥 ${batter}`);
   if (pitcher) lines.push(`⚾ vs ${pitcher}`);
   if (inning) lines.push(`📊 ${inning}`);
   if (desc)   lines.push(desc);
   lines.push("\nHASHTAGS:\n#MLB #HomeRun #Baseball #MLBShorts #Statcast\n");
   lines.push("VIDEOS:");
   lines.push("1. clip");
   lines.push(`   ${$json.d}`);
   lines.push("2. clip");
   lines.push(`   ${$json.a}\n`);
   lines.push("HOME RUN DATA:");
   lines.push(`GamePk: ${gamePk}`);
   lines.push(`Batter: ${batter}`);
   if (inning) lines.push(`Inning: ${inning}`);
   return [{ json: { postText: lines.join("\n") } }];
   ```

12) Write Binary File (Post)
   - Convert postText string → binary → write to MLB_HomeRun_Posts/YYYY-MM-DD/tonights_homer_N_TIMESTAMP.txt
   - Or simpler: use Execute Command to write via heredoc:
   ```bash path=null start=null
   /bin/zsh -lc 'cat > \
   /Users/benbirkhahn/HomerTrakker/MLB_HomeRun_Posts/$(date +%F)/tonights_homer_{{ $json.index }}_$(date +%Y%m%d_%H%M%S).txt <<"EOF"
   {{ $json.postText }}
   EOF'
   ```

13) Execute Command (Download videos)
   - Download with your script so filenames align with compiler expectations
   ```bash path=null start=null
   /bin/zsh -lc '/Users/benbirkhahn/twitter_bot_env/bin/python3 \
     /Users/benbirkhahn/HomerTrakker/download_homer_videos.py $(date +%F)'
   ```

14) Execute Command (Compile Shorts; require both angles)
   ```bash path=null start=null
   /bin/zsh -lc 'export HOMER_REQUIRE_BOTH=1 HOMER_BROADCAST_MAX_SECS=15 HOMER_TOTAL_MAX_SECS=30; \
     /Users/benbirkhahn/twitter_bot_env/bin/python3 \
     /Users/benbirkhahn/HomerTrakker/shorts_video_compiler.py $(date +%F)'
   ```

15) Execute Command (Upload to YouTube non‑interactive)
   ```bash path=null start=null
   /bin/zsh -lc '/Users/benbirkhahn/twitter_bot_env/bin/python3 \
     /Users/benbirkhahn/HomerTrakker/uploader_runner.py $(date +%F)'
   ```

16) Slack/Discord (optional) or Twilio SMS
   - Use n8n’s Slack/Discord/Twilio nodes; populate message with video URL outputs captured from uploader logs or returned metadata (if you parse it)

17) Execute Command (Cleanup sources)
   ```bash path=null start=null
   /bin/zsh -lc '/Users/benbirkhahn/twitter_bot_env/bin/python3 \
     /Users/benbirkhahn/HomerTrakker/cleanup_media.py $(date +%F)'
   ```

## Workflow 2: Nightly Cleanup (03:30)

1) Cron (03:30 daily)
2) Execute Command (remove old compiled videos and clean yesterday)
```bash path=null start=null
/bin/zsh -lc '
  find \
    /Users/benbirkhahn/HomerTrakker/Shorts_Ready -type f -name "*.mp4" -mtime +7 -delete;
  /Users/benbirkhahn/twitter_bot_env/bin/python3 \
    /Users/benbirkhahn/HomerTrakker/cleanup_media.py $(date -v-1d +%F)
'
```

## Notifications

- iMessage (local Mac): Use Execute Command to run osascript, identical to your terminal test.
```applescript path=null start=null
osascript - "+1XXXXXXXXXX" "HomerTrakker: HR detected — {PLAYER} ({INNING})" <<'APPLESCRIPT'
on run argv
  set target to item 1 of argv
  set textMsg to item 2 of argv
  tell application "Messages"
    set targetService to first service whose service type is iMessage
    set targetBuddy to buddy target of targetService
    send textMsg to targetBuddy
  end tell
end run
APPLESCRIPT
```
- Twilio SMS (cloud‑friendly): Use Twilio node and configure credentials in n8n’s Credential store. Never hardcode secrets in commands.

## Upload‑once ledger in n8n

- You can keep using ~/.homer/uploads.json managed by your Python uploader.
- Or mirror it in an n8n Data Store (uploaded:YYYY-MM-DD:NUM). Before uploading, check for presence and skip if found.

## Require both angles policy

- The compiler already enforces both angles under HOMER_REQUIRE_BOTH=1 (we set this in the poller orchestration).
- If you ever want a timed fallback (e.g., after 5 minutes without the second angle, post single‑angle), insert a WAIT→CHECK loop before compile and toggle HOMER_REQUIRE_BOTH to 0 for that specific homer.

## Error handling

- Set “Continue On Fail” on non‑critical steps (e.g., stat enrichment) to keep the workflow moving.
- Add an Error Trigger workflow in n8n to ping you (Slack/Twilio/iMessage) if any step throws.

## Security and secrets

- Put OAuth tokens/keys into n8n Credentials (YouTube, Twilio) or environment variables.
- Don’t echo or log secret values.
- For iMessage, macOS will prompt once to allow automation; accept it.

## Appendix A: Minimal Function node snippets

Select 4000K broadcast and a darkroom clip, return both or none:
```javascript path=null start=null
const items = $json.highlights?.highlights?.items || [];
const prefer4000K = urls => urls.find(u=>u.includes('4000K')) || urls[0] || null;
const batterId = $item(0).$node["Function"].json.play?.matchup?.batter?.id;

const candidates = items.filter(it => {
  const isHR = (it.headline||it.title||'').toLowerCase().includes('home run');
  const hasBatter = (it.keywordsAll||[]).some(k => k.type==='player' && String(k.playerId)===String(batterId));
  return isHR && hasBatter;
});
let links = [];
for (const it of candidates) {
  for (const pb of (it.playbacks||[])) {
    const url = pb.url||''; if (url.endsWith('.mp4')) links.push(url);
  }
}
const diamond = links.filter(u=>u.includes('mlb-cuts-diamond.mlb.com'));
const darkroom= links.filter(u=>u.includes('darkroom-clips.mlb.com'));
const d = prefer4000K(diamond);
const a = darkroom[0]||null;
return (d && a) ? [{ json:{ d, a } }] : [];
```

Check/upload‑once ledger from Data Store:
```javascript path=null start=null
const date = $json.date; // YYYY-MM-DD
const num  = $json.homerNum;
const key = `uploaded:${date}:${num}`;
const store = await this.getWorkflowStaticData('global');
if (store[key]) {
  return []; // already uploaded
}
store[key] = { at: new Date().toISOString() };
return [{ json: { ok: true } }];
```

## Appendix B: Using your existing Python scripts from n8n

For maximum reliability and minimal rebuild, prefer calling your battle‑tested scripts:
- Detect/backfill/enrich/download/compile/upload/cleanup are already wired in:
  - homer_minute_poller.py (sets live window logic and runs the pipeline idempotently)
  - shorts_video_compiler.py enforces HOMER_REQUIRE_BOTH
  - youtube_homer_bot.py handles upload + ledger + notifications

Wrap them with Execute Command nodes as shown above and you’ll get n8n orchestration with the same behavior you trust today.
