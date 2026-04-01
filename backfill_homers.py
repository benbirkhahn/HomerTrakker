#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
Backfill MLB Home Runs over a date range and run the HomerTrakker workflow.

Features:
- Iterates dates between --start and --end (defaults to last 30 days)
- For each date, finds all games and extracts home_run events from game feeds
- Creates post files with broadcast (prefer 4000K) + animated URLs when available
- Runs statcast_enricher.py, download_homer_videos.py (with retry), shorts_video_compiler.py
- Optionally runs uploader_runner.py (when --upload is passed) — beware YouTube API quotas

Usage examples:
  python3 backfill_homers.py --days 30                # last 30 days (no uploads)
  python3 backfill_homers.py --start 2025-09-01 --end 2025-09-29 --upload
  HOMER_REQUIRE_BOTH=0 HOMER_RETRY_ANIMATED=1 python3 backfill_homers.py --days 7

Notes:
- Respects ~/.homer/state.json to dedupe seen plays (seen:{gamePk}:{atBatIndex}).
- Uses gamePk for post file number to avoid collisions across multiple HRs per game.
- YouTube uploads can easily exceed daily quota — consider running without --upload first
  and uploading gradually.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import subprocess

BASE_DIR = Path(__file__).resolve().parent
API_BASE = "https://statsapi.mlb.com/api/v1"
STATE_DIR = Path.home() / ".homer"
STATE_PATH = STATE_DIR / "state.json"


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
    return {"seen": {}, "video_retries": {}}


def save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save state: {e}")


def collect_games_for_date(date_str: str) -> List[Dict[str, Any]]:
    sch = http_get_json(f"{API_BASE}/schedule", {"sportId": 1, "date": date_str, "hydrate": "team,linescore"})
    games: List[Dict[str, Any]] = []
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


def get_homer_videos(game_pk: int, batter_id: Optional[int], batter_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Get videos for a homer from MLB Content API. Return (broadcast_url, animated_url)."""
    try:
        content = http_get_json(f"{API_BASE}/game/{game_pk}/content")
        items = (content.get("highlights", {}) or {}).get("highlights", {}).get("items", [])

        def is_hr_item(it: Dict[str, Any]) -> bool:
            t = (it.get("headline") or it.get("title") or "").lower()
            return "home run" in t

        def by_batter(it: Dict[str, Any]) -> bool:
            if batter_id:
                for kw in it.get("keywordsAll", []) or []:
                    if kw.get("type") == "player" and str(kw.get("playerId")) == str(batter_id):
                        return True
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
        if not (d or a) and os.getenv("HOMER_ALLOW_PRODUCED") == "1":
            d = produced[0] if produced else d
        return d, a
    except Exception as e:
        print(f"⚠️  Content API error for game {game_pk}: {e}")
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


def write_post_file(date_str: str, game_pk: int, at_bat_index: int, text: str) -> Path:
    date_dir = BASE_DIR / "MLB_HomeRun_Posts" / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = date_dir / f"tonights_homer_{game_pk}-{at_bat_index}_{ts}.txt"
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


def daterange(start: datetime, end: datetime):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", dest="start_date", help="YYYY-MM-DD start date")
    parser.add_argument("--end", dest="end_date", help="YYYY-MM-DD end date")
    parser.add_argument("--days", type=int, default=30, help="If start/end not given, backfill last N days (default 30)")
    parser.add_argument("--upload", action="store_true", help="Also run uploader_runner.py (beware YouTube quotas)")
    parser.add_argument("--require-both", action="store_true", help="Require both broadcast + animated before creating a post")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between dates to avoid rate limits")
    parser.add_argument("--force-posts", action="store_true", help="Create posts even if play key is already marked seen")
    args = parser.parse_args()

    # Compute date range
    if args.start_date and args.end_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
        end = datetime.strptime(args.end_date, "%Y-%m-%d")
    else:
        end = datetime.now()
        start = end - timedelta(days=args.days - 1)

    # Informative settings
    print(f"📅 Backfill range: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
    print(f"📼 Require both angles: {'ON' if args.require_both else 'OFF'} (override with --require-both)")
    print(f"🔁 Animated retry: {'ON' if os.getenv('HOMER_RETRY_ANIMATED') == '1' else 'OFF'} (set HOMER_RETRY_ANIMATED=1 to enable)")
    print(f"📤 YouTube upload: {'ON' if args.upload else 'OFF'} (pass --upload to enable)")

    state = load_state()
    seen = state.get("seen", {})
    video_retries = state.get("video_retries", {})

    py = str(Path("/Users/benbirkhahn/twitter_bot_env/bin/python3"))

    for d in daterange(start, end):
        date_str = d.strftime("%Y-%m-%d")
        print("\n=== 🗓️  Processing date:", date_str, "===")

        # Gather all games for date
        games = collect_games_for_date(date_str)
        print(f"🧾 Games: {len(games)}")

        # Build posts for each homer found
        new_posts = 0
        for g in games:
            game_pk = g.get("gamePk")
            if not game_pk:
                continue
            hrs = find_hr_plays(game_pk)
            for p in hrs:
                about = p.get("about", {})
                key = f"{game_pk}:{about.get('atBatIndex')}"
                if seen.get(key) and not args.force_posts:
                    continue
                batter_id = ((p.get("matchup") or {}).get("batter") or {}).get("id")
                batter_name = ((p.get("matchup") or {}).get("batter") or {}).get("fullName") or "Unknown Player"
                b_url, a_url = get_homer_videos(game_pk, batter_id, batter_name)

                # Policy: require both or at least one
                if args.require_both and not (b_url and a_url):
                    # Skip for now but keep retry count for videos
                    video_retries[key] = video_retries.get(key, 0) + 1
                    print(f"⏭️  Skipping (require both) {batter_name} — {key}")
                    continue
                if not (b_url or a_url):
                    # No videos yet — increment retry
                    video_retries[key] = video_retries.get(key, 0) + 1
                    print(f"⏳ No videos yet for {batter_name} — {key} (retry {video_retries[key]})")
                    continue

                text = build_post_text(p, game_pk, b_url or "", a_url or "")
                write_post_file(date_str, game_pk, int(about.get('atBatIndex') or 0), text)
                seen[key] = True
                if key in video_retries:
                    del video_retries[key]
                new_posts += 1

        # Save state after creating posts
        state["seen"] = seen
        state["video_retries"] = video_retries
        save_state(state)

        print(f"📝 New posts created for {date_str}: {new_posts}")

        # Run enrich → download → compile for this date
        # Enable animated retry via env HOMER_RETRY_ANIMATED=1 if desired
        run_step([py, str(BASE_DIR / "statcast_enricher.py"), date_str])

        dl_cmd = [py, str(BASE_DIR / "download_homer_videos.py"), date_str]
        if os.getenv("HOMER_RETRY_ANIMATED") == "1":
            dl_cmd += ["--retry-animated", "--retry-count", os.getenv("HOMER_RETRY_COUNT", "3"), "--retry-delay", os.getenv("HOMER_RETRY_DELAY", "2")]
        run_step(dl_cmd)

        run_step([py, str(BASE_DIR / "shorts_video_compiler.py"), date_str])

        # Optional uploader
        if args.upload or os.getenv("HOMER_AUTO_UPLOAD") == "1":
            run_step([py, str(BASE_DIR / "uploader_runner.py"), date_str])

        # Friendly sleep to reduce API pressure if requested
        if args.sleep > 0:
            time.sleep(args.sleep)

    print("\n✅ Backfill complete.")


if __name__ == "__main__":
    main()
