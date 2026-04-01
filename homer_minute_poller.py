#!/Users/benbirkhahn/twitter_bot_env/bin/python3
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
- HOMER_NOTIFY_PHONE=+1XXXXXXXXXX   # optional: iMessage number for detection/upload notifications

Notes:
- Uses ~/.homer/state.json to dedupe seen plays (seen:{gamePk}:{atBatIndex}).
- Writes posts to MLB_HomeRun_Posts/YYYY-MM-DD/tonights_homer_N_YYYYMMDD_HHMMSS.txt
- Delegates enrichment/compile/upload to existing scripts in the repo.
"""

import json
import os
import re
import glob
from homer_timing_logger import timing_logger
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import urllib.request
import urllib.parse

BASE_DIR = Path(__file__).resolve().parent
API_BASE = "https://statsapi.mlb.com/api/v1"
STATE_DIR = Path.home() / ".homer"
STATE_PATH = STATE_DIR / "state.json"

PRE_MIN = 10      # minutes before scheduled start
POST_HOURS = 6    # hours after scheduled start


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


def get_homer_videos(game_pk: int, batter_id: Optional[int], batter_name: str, homer_num: int) -> Tuple[Optional[str], Optional[str]]:
    """Get videos for a homer from multiple sources. Return (broadcast_url, animated_url)."""
    
    # First try MLB Content API
    try:
        content = http_get_json(f"{API_BASE}/game/{game_pk}/content")
        items = (content.get("highlights", {}) or {}).get("highlights", {}).get("items", [])
        
        def is_hr_item(it: Dict[str, Any]) -> bool:
            t = (it.get("headline") or it.get("title") or "").lower()
            return "home run" in t
        
        def by_batter(it: Dict[str, Any]) -> bool:
            # Check player ID
            if batter_id:
                for kw in it.get("keywordsAll", []) or []:
                    if kw.get("type") == "player" and str(kw.get("playerId")) == str(batter_id):
                        return True
            # Fallback to name match
            t = (it.get("headline") or it.get("title") or "").lower()
            return batter_name.lower() in t
        
        urls: List[str] = []
        for it in items:
            if not (is_hr_item(it) and by_batter(it)):
                continue
            for pb in it.get("playbacks", []) or []:
                url = pb.get("url") or ""
                if url.endswith(".mp4"):
                    urls.append(url)
        
        diamond = [u for u in urls if "mlb-cuts-diamond.mlb.com" in u]
        darkroom = [u for u in urls if "darkroom-clips.mlb.com" in u]
        produced = [u for u in urls if "bdata-producedclips.mlb.com" in u]
        
        def pick_4000k_or_first(arr: List[str]) -> Optional[str]:
            for u in arr:
                if "4000K" in u:
                    return u
            return arr[0] if arr else None
        
        d = pick_4000k_or_first(diamond)
        a = darkroom[0] if darkroom else None
        if d or a:
            if not (d or a) and os.getenv("HOMER_ALLOW_PRODUCED") == "1":
                d = produced[0] if produced else d
            return d, a
    except Exception as e:
        print(f"⚠️  Content API error: {e}")
    
    # If we don't have videos yet, try MLB.com
    try:
        # Construct MLB.com search URL
        search_url = f"https://www.mlb.com/video/search?q={urllib.parse.quote(f'{batter_name} home run')}"
        # TODO: Implement direct MLB.com scraping
        # For now, just print the URL we would check
        print(f"🔍 MLB.com videos to check: {search_url}")
    except Exception as e:
        print(f"⚠️  MLB.com search error: {e}")
    
    # No videos found from any source
    return None, None


def build_post_text(play: Dict[str, Any], game_pk: int, d: str, a: str) -> str:
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


def notify_imessage(msg: str) -> None:
    phone = os.getenv("HOMER_NOTIFY_PHONE") or os.getenv("HOMER_NOTIFY_IMESSAGE")
    if not phone:
        return
    try:
        script = (
            "on run argv\n"
            "  set target to item 1 of argv\n"
            "  set textMsg to item 2 of argv\n"
            "  tell application \"Messages\"\n"
            "    set targetService to first service whose service type is iMessage\n"
            "    set targetBuddy to buddy target of targetService\n"
            "    send textMsg to targetBuddy\n"
            "  end tell\n"
            "end run\n"
        )
        subprocess.run(["osascript", "-", phone, msg], input=script, text=True, capture_output=True, check=True)
    except Exception as e:
        print(f"⚠️  iMessage notify failed: {e}")


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
            batter_id = ((p.get("matchup") or {}).get("batter") or {}).get("id")
            batter_name = ((p.get("matchup") or {}).get("batter") or {}).get("fullName") or "Unknown Player"
            inning = f"{about.get('halfInning','')} {about.get('inning','')}".strip()
            
            # Try to get videos
            retry_count = video_retries.get(key, 0)
            d, a = get_homer_videos(game_pk, batter_id, batter_name, retry_count)
            
            # If we have at least one video, create the post
            if d or a:
                text = build_post_text(p, game_pk, d or "", a or "")
                write_post_file(today, text)
                seen[key] = True
                new_posts += 1
                notify_imessage(f"HomerTrakker: HR detected — {batter_name} ({inning})")
                # Reset retry count on success
                if key in video_retries:
                    del video_retries[key]
            else:
                # No videos yet, increment retry count
                video_retries[key] = retry_count + 1
                print(f"⏳ No videos yet for {batter_name} homer ({inning}) - retry {retry_count + 1}")

    # Save state if updated
    state["seen"] = seen
    save_state(state)

    # If no new posts, still run downstream for any manually created posts
    print(f"🧾 New posts created this run: {new_posts}")

    py = str(Path("/Users/benbirkhahn/twitter_bot_env/bin/python3"))

    # Enrich
    run_step([py, str(BASE_DIR / "statcast_enricher.py"), today])

    # Download (with optional animated retry)
    dl_cmd = [py, str(BASE_DIR / "download_homer_videos.py"), today]
    if os.getenv("HOMER_RETRY_ANIMATED") == "1":
        dl_cmd += ["--retry-animated", "--retry-count", os.getenv("HOMER_RETRY_COUNT", "3"), "--retry-delay", os.getenv("HOMER_RETRY_DELAY", "2")]
    run_step(dl_cmd)

    # Compile (env caps respected by shorts_video_compiler)
    run_step([py, str(BASE_DIR / "shorts_video_compiler.py"), today])

    # Upload (optional)
    if os.getenv("HOMER_AUTO_UPLOAD") == "1":
        run_step([py, str(BASE_DIR / "uploader_runner.py"), today])


if __name__ == "__main__":
    main()
