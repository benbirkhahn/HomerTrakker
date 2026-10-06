#!/Users/benbirkhahn/HomerTrakker/twitter_bot_env/bin/python3
"""
HomerTrakker Minute Poller
- Detects MLB home runs during live windows (10 min pre-game to 6 hours post start)
- Creates post files with broadcast (prefer 4000K) + animated URLs when both are available
- Orchestrates enrich → download → compile → upload (optional) for today's date

Env vars:
- HOMER_PAUSE=1                     # optional: exit early
- HOMER_REQUIRE_BOTH=1              # require both broadcast + animated before compiling
- HOMER_BROADCAST_MAX_SECS=15       # cap for first (broadcast) segment
- HOMER_TOTAL_MAX_SECS=30           # total cap for concatenated segments
- HOMER_AUTO_UPLOAD=1               # automatically upload via uploader_runner.py
- HOMER_ALLOW_PRODUCED=1            # optionally allow producedclips fallback when no diamond/darkroom

Notes:
- Uses ~/.homer/state.json to dedupe seen plays (seen:{gamePk}:{atBatIndex}).
- Writes posts to MLB_HomeRun_Posts/YYYY-MM-DD/tonights_homer_N_YYYYMMDD_HHMMSS.txt
- Delegates enrichment/compile/upload to existing scripts in the repo.
"""

import json
import subprocess
import os
import re
import glob
import sys
from homer_timing_logger import timing_logger
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import urllib.request
import urllib.parse
from homer_clip_matcher import select_homer_clip

BASE_DIR = Path(__file__).resolve().parent
API_BASE = "https://statsapi.mlb.com/api/v1"
STATE_DIR = Path.home() / ".homer"
STATE_PATH = STATE_DIR / "state.json"

PRE_MIN = 10      # minutes before scheduled start
POST_HOURS = 6    # hours after scheduled start


def load_local_env(path: Path = BASE_DIR / ".homer.env") -> None:
    try:
        if not path.exists():
            return
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = re.sub(r"\s+#.*$", "", value).strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except Exception as e:
        print(f"⚠️  Could not load local env file {path}: {e}")


load_local_env()


def http_get_json(url: str, params: Dict[str, Any] = None, timeout: int = 20) -> Dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            with open(STATE_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save state: {e}")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_live_window(game: Dict[str, Any], now: datetime) -> bool:
    gd = game.get("gameDate")
    if not gd:
        return False
    try:
        # gameDate is ISO string, typically Zulu
        start = datetime.fromisoformat(gd.replace("Z", "+00:00"))
    except Exception:
        return False
    pre = timedelta(minutes=PRE_MIN)
    post = timedelta(hours=POST_HOURS)
    return (start - pre) <= now <= (start + post)


def collect_games_for_dates(dates: List[str]) -> List[Dict[str, Any]]:
    games: List[Dict[str, Any]] = []
    for d in dates:
        sch = http_get_json(f"{API_BASE}/schedule", {"sportId": 1, "date": d, "hydrate": "team,linescore"})
        for date in sch.get("dates", []):
            for g in date.get("games", []):
                games.append(g)
    return games


def find_hr_plays(game_pk: int) -> List[Dict[str, Any]]:
    feed = http_get_json(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    hrs = []
    for p in plays:
        if p.get("result", {}).get("eventType") == "home_run":
            hrs.append(p)
    return hrs


def get_homer_videos(
    game_pk: int,
    play: Dict[str, Any],
    all_hr_plays: List[Dict[str, Any]],
    used_clip_ids: set,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """Get videos for a homer from multiple sources. Return (broadcast_url, animated_url)."""
    
    # First try MLB Content API
    try:
        content = http_get_json(f"{API_BASE}/game/{game_pk}/content")
        d, a, debug = select_homer_clip(content, play, all_hr_plays, used_clip_ids)
        if d or a:
            return d, a, debug
    except Exception as e:
        print(f"⚠️  Content API error: {e}")
    
    # If we don't have videos yet, try MLB.com
    try:
        # Construct MLB.com search URL
        batter_name = ((play.get("matchup") or {}).get("batter") or {}).get("fullName") or ""
        search_url = f"https://www.mlb.com/video/search?q={urllib.parse.quote(f'{batter_name} home run')}"
        # TODO: Implement direct MLB.com scraping
        # For now, just print the URL we would check
        print(f"🔍 MLB.com videos to check: {search_url}")
    except Exception as e:
        print(f"⚠️  MLB.com search error: {e}")
    
    # No videos found from any source
    return None, None, {"matchedBy": "notFound", "pickedFrom": "", "clipGuid": "", "atBatIndex": (play.get("about") or {}).get("atBatIndex")}


def build_post_text(play: Dict[str, Any], game_pk: int, d: str, a: str, debug: Dict[str, Any] = None) -> str:
    matchup = play.get("matchup", {})
    batter = (matchup.get("batter") or {}).get("fullName") or "Unknown Player"
    pitcher = (matchup.get("pitcher") or {}).get("fullName") or ""
    about = play.get("about", {})
    inning = f"{about.get('halfInning','')} {about.get('inning','')}".strip()
    desc = play.get("result", {}).get("description") or ""

    lines = []
    lines.append("TONIGHT'S HOME RUN - READY FOR @homertrakker")
    lines.append("=======================================================\n")
    lines.append("CAPTION:")
    lines.append("🏠⚾ HOME RUN ALERT! ⚾🏠")
    lines.append(f"🔥 {batter}")
    if pitcher:
        lines.append(f"⚾ vs {pitcher}")
    if inning:
        lines.append(f"📊 {inning}")
    if desc:
        lines.append(desc)
    lines.append("\nHASHTAGS:\n#MLB #HomeRun #Baseball #MLBShorts #Statcast\n")
    lines.append("VIDEOS:")
    lines.append("1. clip")
    lines.append(f"   {d}")
    if a:
        lines.append("2. clip")
        lines.append(f"   {a}\n")
    lines.append("HOME RUN DATA:")
    lines.append(f"GamePk: {game_pk}")
    lines.append(f"Batter: {batter}")
    if inning:
        lines.append(f"Inning: {inning}")
    if debug:
        lines.append(f"AtBatIndex: {debug.get('atBatIndex', about.get('atBatIndex'))}")
        lines.append(f"ClipGuid: {debug.get('clipGuid', '')}")
        lines.append(f"MatchedBy: {debug.get('matchedBy', '')}")
        lines.append(f"PickedFrom: {debug.get('pickedFrom', '')}")
    return "\n".join(lines) + "\n"


def write_post_file(date_str: str, text: str) -> Path:
    date_dir = BASE_DIR / "MLB_HomeRun_Posts" / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    # Determine next homer number
    nums: List[int] = []
    for p in date_dir.glob("tonights_homer_*.txt"):
        m = re.search(r"tonights_homer_(\d+)_", p.name)
        if m:
            try:
                nums.append(int(m.group(1)))
            except Exception:
                pass
    next_num = (max(nums) + 1) if nums else 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = date_dir / f"tonights_homer_{next_num}_{ts}.txt"
    with open(out, "w") as f:
        f.write(text)
    print(f"📝 Post created: {out}")
    return out


def run_step(cmd: List[str], env: Dict[str, str] = None, ignore_error: bool = True) -> None:
    try:
        print("$", " ".join(cmd))
        subprocess.run(cmd, check=not ignore_error, env={**os.environ, **(env or {})}, capture_output=False)
    except Exception as e:
        print(f"⚠️  Step failed: {e}")


def main():
    if os.getenv("HOMER_PAUSE") == "1" or Path("/tmp/homer_pause").exists():
        print("⏸️  HOMER_PAUSE active — exiting early")
        return

    now = datetime.now(timezone.utc)
    today = now.astimezone().strftime("%Y-%m-%d")
    yday = (now - timedelta(days=1)).astimezone().strftime("%Y-%m-%d")

    print(f"📅 Window dates: {yday}, {today}")

    state = load_state()
    seen = state.get("seen", {})
    video_retries = state.get("video_retries", {})
    assigned_clips = state.get("assigned_clips", {})
    used_clip_ids = {str(v) for v in assigned_clips.values() if v}
    require_both = env_flag("HOMER_REQUIRE_BOTH", default=True)

    games = collect_games_for_dates([yday, today])
    active = [g for g in games if is_live_window(g, now)]
    print(f"🎮 Active-in-window games: {len(active)}")

    new_posts = 0
    for g in active:
        game_pk = g.get("gamePk")
        if not game_pk:
            continue
        
        # First get all homers from game data
        hrs = find_hr_plays(game_pk)
        print(f"⚾ Found {len(hrs)} home runs in game {game_pk}")
        
        for p in hrs:
            about = p.get("about", {})
            key = f"{game_pk}:{about.get('atBatIndex')}"
            
            # Skip if we've already processed this homer
            if seen.get(key):
                continue
            
            # Get batter info
            batter_name = ((p.get("matchup") or {}).get("batter") or {}).get("fullName") or "Unknown Player"
            inning = f"{about.get('halfInning','')} {about.get('inning','')}".strip()
            
            # Try to get videos
            retry_count = video_retries.get(key, 0)
            d, a, debug = get_homer_videos(game_pk, p, hrs, used_clip_ids)
            
            if require_both and not (d and a):
                video_retries[key] = retry_count + 1
                missing = "animated" if d else "broadcast"
                print(f"⏳ Waiting for {missing} clip for {batter_name} homer ({inning}) - retry {retry_count + 1}")
            elif d or a:
                text = build_post_text(p, game_pk, d or "", a or "", debug)
                write_post_file(today, text)
                seen[key] = True
                clip_guid = debug.get("clipGuid")
                if clip_guid:
                    assigned_clips[key] = clip_guid
                    used_clip_ids.add(str(clip_guid))
                new_posts += 1
                # Reset retry count on success
                if key in video_retries:
                    del video_retries[key]
            else:
                # No videos yet, increment retry count
                video_retries[key] = retry_count + 1
                print(f"⏳ No videos yet for {batter_name} homer ({inning}) - retry {retry_count + 1}")

    # Save state if updated
    state["seen"] = seen
    state["video_retries"] = video_retries
    state["assigned_clips"] = assigned_clips
    save_state(state)

    # If no new posts, still run downstream for any manually created posts
    print(f"🧾 New posts created this run: {new_posts}")

    py = sys.executable

    # Enrich
    run_step([py, str(BASE_DIR / "statcast_enricher.py"), today])

    # Download (with optional animated retry)
    dl_cmd = [py, str(BASE_DIR / "download_homer_videos.py"), today]
    if os.getenv("HOMER_RETRY_ANIMATED") == "1":
        dl_cmd += ["--retry-animated", "--retry-count", os.getenv("HOMER_RETRY_COUNT", "3"), "--retry-delay", os.getenv("HOMER_RETRY_DELAY", "2")]
    run_step(dl_cmd)

    # Compile (env caps respected by shorts_video_compiler)
    compile_cmd = [py, str(BASE_DIR / "shorts_video_compiler.py"), today]
    if require_both:
        compile_cmd.append("--require-both")
    run_step(compile_cmd)

    # Keep scheduled YouTube queue optimized even when no new upload is created.
    run_step([py, str(BASE_DIR / "youtube_queue_monitor.py"), "--apply"])

    # Upload (optional)
    if os.getenv("HOMER_AUTO_UPLOAD") == "1":
        run_step([py, str(BASE_DIR / "uploader_runner.py"), today])


if __name__ == "__main__":
    main()
