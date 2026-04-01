#!/usr/bin/env python3
"""
Yankees Game Clip Extractor
- Extracts clips from specified Yankees game
- Uses HomerTrakker infrastructure for processing
- Supports both home runs and other significant plays
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.request
import urllib.parse

# Import HomerTrakker utilities
from homer_minute_poller import http_get_json
from download_homer_videos import download_video, extract_video_urls_from_file
from shorts_video_compiler import ShortsCompiler

BASE_DIR = Path(__file__).resolve().parent
API_BASE = "https://statsapi.mlb.com/api/v1"
YANKEES_TEAM_ID = 147

def get_yankees_game(target_date):
    """Get Yankees game data for specified date."""
    date_str = target_date.strftime("%Y-%m-%d")
    games = http_get_json(f"{API_BASE}/schedule", {
        "sportId": 1,
        "date": date_str,
        "teamId": YANKEES_TEAM_ID,
        "teamIds": ["147", "111"],  # Yankees and Red Sox
        "hydrate": "team,linescore"
    })
    
    for date in games.get("dates", []):
        for game in date.get("games", []):
            return game
    return None

def get_game_plays(game_pk):
    """Get all plays from game feed."""
    feed = http_get_json(f"{API_BASE}/game/{game_pk}/feed/live")
    return feed.get("liveData", {}).get("plays", {}).get("allPlays", [])

def is_significant_play(play):
    """Determine if a play is significant enough to clip."""
    result = play.get("result", {})
    event = result.get("eventType")
    
    # Always include home runs
    if event == "home_run":
        return True
        
    # Include other significant plays based on event type
    significant_events = {
        "triple", "double", "stolen_base_home", "pickoff_caught_stealing_home",
        "caught_stealing_home", "wild_pitch", "passed_ball"
    }
    if event in significant_events:
        return True
        
    # Include plays with runs scored
    if result.get("rbi", 0) > 0:
        return True
    
    return False

def get_play_videos(game_pk, play):
    """Get available video URLs for a play."""
    content = http_get_json(f"{API_BASE}/game/{game_pk}/content")
    items = (content.get("highlights", {}) or {}).get("highlights", {}).get("items", [])
    
    # Match videos to play
    play_desc = play.get("result", {}).get("description", "").lower()
    batter = (play.get("matchup", {}).get("batter", {}).get("fullName", "") or "").lower()
    
    matching_videos = []
    for item in items:
        title = (item.get("headline") or item.get("title") or "").lower()
        if not (batter in title or any(word in title for word in play_desc.split())):
            continue
            
        for pb in item.get("playbacks", []) or []:
            url = pb.get("url")
            if url and url.endswith(".mp4"):
                matching_videos.append(url)
    
    # Separate into broadcast and animated clips
    diamond = [u for u in matching_videos if "mlb-cuts-diamond.mlb.com" in u]
    darkroom = [u for u in matching_videos if "darkroom-clips.mlb.com" in u]
    
    def pick_4000k_or_first(arr):
        for u in arr:
            if "4000K" in u:
                return u
        return arr[0] if arr else None
    
    return pick_4000k_or_first(diamond), darkroom[0] if darkroom else None

def process_game_plays(game_pk, output_dir):
    """Process all significant plays from a game."""
    plays = get_game_plays(game_pk)
    significant_plays = [p for p in plays if is_significant_play(p)]
    
    print(f"Found {len(significant_plays)} significant plays to process")
    
    # Create output directories
    videos_dir = output_dir / "videos"
    processed_dir = output_dir / "processed"
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)
    
    play_data = []
    for i, play in enumerate(significant_plays, 1):
        print(f"\nProcessing play {i}/{len(significant_plays)}")
        
        # Get basic play info
        about = play.get("about", {})
        result = play.get("result", {})
        matchup = play.get("matchup", {})
        
        play_info = {
            "index": i,
            "inning": f"{about.get('halfInning', '')} {about.get('inning', '')}".strip(),
            "description": result.get("description", ""),
            "event_type": result.get("eventType", ""),
            "batter": (matchup.get("batter", {}) or {}).get("fullName", ""),
            "pitcher": (matchup.get("pitcher", {}) or {}).get("fullName", ""),
        }
        
        # Get video URLs
        broadcast_url, animated_url = get_play_videos(game_pk, play)
        if not (broadcast_url or animated_url):
            print(f"No videos found for play {i}")
            continue
            
        # Download videos
        play_info["videos"] = []
        if broadcast_url:
            filename = f"play_{i}_1_broadcast.mp4"
            path = videos_dir / filename
            if download_video(broadcast_url, str(path)):
                play_info["videos"].append(str(path))
                
        if animated_url:
            filename = f"play_{i}_2_animated.mp4"
            path = videos_dir / filename
            if download_video(animated_url, str(path)):
                play_info["videos"].append(str(path))
        
        if play_info["videos"]:
            play_data.append(play_info)
    
    # Save play metadata
    with open(output_dir / "metadata.json", "w") as f:
        json.dump({
            "game_pk": game_pk,
            "plays": play_data
        }, f, indent=2)
    
    return play_data

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract clips from Yankees game")
    parser.add_argument("--date", help="Game date (YYYY-MM-DD). Defaults to yesterday.")
    parser.add_argument("--open", action="store_true", help="Open output folder when done")
    args = parser.parse_args()
    
    # Default to Yankees vs Red Sox game from October 1st, 2025
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime(2025, 10, 1)
    
    print(f"🎯 Looking for Yankees game on {target_date.strftime('%Y-%m-%d')}")
    
    # Get game data
    game = get_yankees_game(target_date)
    if not game:
        print("❌ No Yankees game found for specified date")
        return
    
    game_pk = game.get("gamePk")
    if not game_pk:
        print("❌ Invalid game data")
        return
        
    # Create output directory
    date_str = target_date.strftime("%Y-%m-%d")
    output_dir = BASE_DIR / "game_clips" / f"{date_str}_NYY"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"📂 Output directory: {output_dir}")
    print(f"🎮 Processing game {game_pk}")
    
    # Process plays and download videos
    play_data = process_game_plays(game_pk, output_dir)
    if not play_data:
        print("❌ No plays processed")
        return
    
    print(f"\n✅ Processed {len(play_data)} plays")
    
    # Open output directory if requested
    if args.open:
        import subprocess
        subprocess.run(["open", str(output_dir)])

if __name__ == "__main__":
    main()