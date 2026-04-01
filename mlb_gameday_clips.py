#!/usr/bin/env python3
"""
MLB Game Day Clip Extractor
- Uses MLB Game Day feed for alternative angles
- Includes StatCast overlays and data
- Supports high resolution downloads
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import urllib.parse
import time
import subprocess

class MLBGameDay:
    def __init__(self, game_date=None, team_id=None):
        self.date = game_date or (datetime.now() - timedelta(days=1)).date()
        self.team_id = team_id or 147  # Default to Yankees
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.gameday_url = "https://www.mlb.com/gameday"
        self.output_dir = Path.home() / "game_clips" / "gameday"
        
    def _make_request(self, url, params=None):
        """Make an API request with proper error handling."""
        try:
            if params:
                processed = {k: ','.join(map(str, v)) if isinstance(v, list) else v 
                           for k, v in params.items()}
                url = f"{url}?{urllib.parse.urlencode(processed)}"
            
            print(f"📡 Requesting: {url}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.mlb.com/gameday"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"⚠️  Request failed: {e}")
            return {}

    def get_game(self):
        """Get game data for the specified date and team."""
        params = {
            "sportId": 1,
            "date": self.date.strftime("%Y-%m-%d"),
            "teamId": self.team_id,
            "hydrate": "game(content),probablePitcher(note)"
        }
        data = self._make_request(f"{self.base_url}/schedule", params)
        
        for date in data.get("dates", []):
            for game in date.get("games", []):
                return game
        return None

    def get_game_feed(self, game_pk):
        """Get detailed game feed with all plays and angles."""
        return self._make_request(f"{self.base_url}/game/{game_pk}/feed/live")

    def get_play_by_play(self, game_pk):
        """Get play-by-play data with video timestamps."""
        return self._make_request(f"{self.base_url}/game/{game_pk}/playByPlay")

    def get_best_video_url(self, playbacks):
        """Get highest quality video URL available."""
        quality_order = ["4K", "2160p", "4000K", "1080p", "720p"]
        urls = {}
        
        for pb in playbacks:
            url = pb.get("url", "")
            if not url or not url.endswith(".mp4"):
                continue
                
            # Check quality markers
            for quality in quality_order:
                if quality in url:
                    urls[quality] = url
                    break
            
            # Check for other high quality indicators
            name = pb.get("name", "").lower()
            if "high" in name:
                urls["high"] = url
        
        # Return highest available quality
        for quality in quality_order:
            if quality in urls:
                return urls[quality]
        
        return urls.get("high") or next(iter(urls.values())) if urls else None

    def download_clip(self, url, output_path, description=""):
        """Download video clip with progress tracking."""
        try:
            print(f"📥 Downloading: {description}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.mlb.com/gameday"
            }
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req) as response:
                total_size = int(response.headers.get('content-length', 0))
                block_size = 8192
                current_size = 0
                
                with open(output_path, 'wb') as f:
                    while True:
                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        current_size += len(chunk)
                        f.write(chunk)
                        
                        # Show progress
                        if total_size > 0:
                            progress = (current_size / total_size) * 100
                            print(f"\rProgress: {progress:.1f}%", end="")
                
                print(f"\n✅ Downloaded: {output_path}")
                return True
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

    def process_plays(self, game_pk):
        """Process and download clips for all significant plays."""
        # Get game data from multiple feeds
        game_feed = self.get_game_feed(game_pk)
        play_by_play = self.get_play_by_play(game_pk)
        
        if not game_feed or not play_by_play:
            print("Unable to get game data")
            return []
        
        # Extract all plays
        plays = game_feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        
        # Create output directories
        date_str = self.date.strftime("%Y-%m-%d")
        output_dir = self.output_dir / f"{date_str}_{self.team_id}"
        videos_dir = output_dir / "videos"
        os.makedirs(videos_dir, exist_ok=True)
        
        processed = []
        
        # Track significant plays
        significant_types = {
            "home_run", "double", "triple", "stolen_base_home",
            "double_play", "triple_play", "pickoff",
            "wild_pitch", "passed_ball"
        }
        
        for idx, play in enumerate(plays, 1):
            result = play.get("result", {})
            event_type = result.get("eventType")
            rbi = result.get("rbi", 0)
            
            # Skip non-significant plays
            if event_type not in significant_types and rbi == 0:
                continue
            
            about = play.get("about", {})
            matchup = play.get("matchup", {})
            
            play_data = {
                "index": idx,
                "inning": f"{about.get('halfInning')} {about.get('inning')}",
                "event": event_type,
                "description": result.get("description"),
                "batter": (matchup.get("batter") or {}).get("fullName"),
                "pitcher": (matchup.get("pitcher") or {}).get("fullName"),
                "videos": []
            }
            
            print(f"\nProcessing Play {idx}: {play_data['description']}")
            
            # Get video content for this play
            content = game_feed.get("liveData", {}).get("content", {})
            highlights = content.get("highlights", {}).get("items", [])
            
            # Match highlights to this play
            matching_highlights = []
            play_desc = play_data['description'].lower()
            for highlight in highlights:
                title = (highlight.get("title") or "").lower()
                desc = (highlight.get("description") or "").lower()
                
                # Match by player names and key terms
                if (play_data['batter'] and play_data['batter'].lower() in title) or \
                   any(word in title for word in play_desc.split()):
                    matching_highlights.append(highlight)
            
            # Process each matching highlight
            for highlight_idx, highlight in enumerate(matching_highlights):
                # Get all available angles
                playbacks = highlight.get("playbacks", [])
                if not playbacks:
                    continue
                
                # Group by angle type
                angles = {}
                for pb in playbacks:
                    angle_type = pb.get("type", "default")
                    if angle_type not in angles:
                        angles[angle_type] = []
                    angles[angle_type].append(pb)
                
                # Download each angle type
                for angle_type, pbs in angles.items():
                    url = self.get_best_video_url(pbs)
                    if not url:
                        continue
                    
                    # Generate filename
                    safe_desc = re.sub(r'[^a-zA-Z0-9]+', '_', play_desc).strip('_')
                    filename = f"play_{idx}_{highlight_idx + 1}_{angle_type}_{safe_desc}.mp4"
                    path = videos_dir / filename
                    
                    if self.download_clip(url, path, f"{play_data['description']} - {angle_type}"):
                        video_info = {
                            "path": str(path),
                            "type": angle_type,
                            "description": highlight.get("description"),
                            "title": highlight.get("title")
                        }
                        play_data["videos"].append(video_info)
            
            if play_data["videos"]:
                processed.append(play_data)
        
        # Save metadata
        if processed:
            meta_path = output_dir / "metadata.json"
            with open(meta_path, "w") as f:
                json.dump({
                    "game_pk": game_pk,
                    "date": date_str,
                    "team_id": self.team_id,
                    "plays": processed
                }, f, indent=2)
            
            print(f"\n✅ Processed {len(processed)} plays")
            print(f"📁 Output directory: {output_dir}")
        
        return processed

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract clips using MLB Game Day feed")
    parser.add_argument("--date", help="Game date (YYYY-MM-DD). Defaults to yesterday.")
    parser.add_argument("--team", type=int, default=147, help="Team ID (default: 147 for Yankees)")
    parser.add_argument("--open", action="store_true", help="Open output folder when done")
    args = parser.parse_args()
    
    # Parse date if provided
    game_date = None
    if args.date:
        try:
            game_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("❌ Invalid date format. Use YYYY-MM-DD")
            return
    
    # Initialize and run
    gameday = MLBGameDay(game_date, args.team)
    
    print(f"🎯 Looking for game on {gameday.date}")
    game = gameday.get_game()
    
    if not game:
        print("❌ No game found for specified date and team")
        return
    
    game_pk = game.get("gamePk")
    if not game_pk:
        print("❌ Invalid game data")
        return
    
    print(f"🎮 Processing game {game_pk}")
    plays = gameday.process_plays(game_pk)
    
    # Open output directory if requested
    if args.open and plays:
        date_str = gameday.date.strftime("%Y-%m-%d")
        output_dir = gameday.output_dir / f"{date_str}_{gameday.team_id}"
        if os.path.exists(output_dir):
            subprocess.run(["open", str(output_dir)])

if __name__ == "__main__":
    main()