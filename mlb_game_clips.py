#!/usr/bin/env python3
"""
MLB Game Clip Extractor
- Fetches and processes clips from MLB games
- Supports Yankees and other teams
- Downloads both broadcast and animated clips
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

class MLBGameClips:
    def __init__(self, game_date=None, team_id=None):
        self.date = game_date or (datetime.now() - timedelta(days=1)).date()
        self.team_id = team_id or 147  # Default to Yankees
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.output_dir = Path.home() / "game_clips"
        
    def _make_request(self, endpoint, params=None):
        """Make an API request with proper error handling."""
        try:
            url = f"{self.base_url}/{endpoint}"
            if params:
                # Convert lists to comma-separated strings
                processed = {k: ','.join(map(str, v)) if isinstance(v, list) else v 
                           for k, v in params.items()}
                url = f"{url}?{urllib.parse.urlencode(processed)}"
            
            print(f"📡 Requesting: {url}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
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
            "hydrate": "team,linescore"
        }
        data = self._make_request("schedule", params)
        
        for date in data.get("dates", []):
            for game in date.get("games", []):
                return game
        return None

    def get_content(self, game_pk):
        """Get content feed for a game."""
        return self._make_request(f"game/{game_pk}/content")

    def get_game_feed(self, game_pk):
        """Get detailed game feed data."""
        return self._make_request(f"game/{game_pk}/feed/live")

    def download_video(self, url, output_path):
        """Download a video file."""
        try:
            print(f"📥 Downloading: {output_path}")
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req) as response:
                with open(output_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            
            print(f"✅ Downloaded: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

    def process_highlights(self, game_pk):
        """Process game highlights and download videos."""
        content = self.get_content(game_pk)
        highlights = (content.get("highlights", {}) or {}).get("highlights", {}).get("items", [])
        
        if not highlights:
            print("No highlights found")
            return []
        
        # Create output directories
        date_str = self.date.strftime("%Y-%m-%d")
        output_dir = self.output_dir / f"{date_str}_{self.team_id}"
        videos_dir = output_dir / "videos"
        os.makedirs(videos_dir, exist_ok=True)
        
        processed = []
        for idx, item in enumerate(highlights, 1):
            title = item.get("headline", "") or item.get("title", "")
            if not title:
                continue
                
            print(f"\nProcessing highlight {idx}: {title}")
            
            # Get video URLs
            urls = []
            for pb in item.get("playbacks", []) or []:
                url = pb.get("url", "")
                if url and url.endswith(".mp4"):
                    urls.append(url)
            
            if not urls:
                print("No video URLs found")
                continue
            
            # Categorize URLs
            diamond = [u for u in urls if "mlb-cuts-diamond.mlb.com" in u]
            darkroom = [u for u in urls if "darkroom-clips.mlb.com" in u]
            
            def pick_best_quality(urls):
                # Quality preference order
                qualities = ["4K", "2160", "4000K", "1080p", "720p"]
                
                for quality in qualities:
                    for url in urls:
                        if quality in url:
                            return url
                return urls[0] if urls else None
            
            # Download videos
            highlight_data = {
                "title": title,
                "videos": [],
                "quality_info": {}
            }
            
            # Try broadcast angle first
            broadcast_url = pick_best_quality(diamond)
            if broadcast_url:
                filename = f"highlight_{idx}_1_broadcast.mp4"
                path = videos_dir / filename
                if self.download_video(broadcast_url, path):
                    highlight_data["videos"].append(str(path))
                    # Add quality info
                    if "4K" in broadcast_url:
                        quality = "4K"
                    elif "2160" in broadcast_url:
                        quality = "2160p"
                    elif "4000K" in broadcast_url:
                        quality = "4000K"
                    elif "1080p" in broadcast_url:
                        quality = "1080p"
                    elif "720p" in broadcast_url:
                        quality = "720p"
                    else:
                        quality = "unknown"
                    highlight_data["quality_info"][str(path)] = quality
            
            # Then try animated/alternate angle
            animated_url = darkroom[0] if darkroom else None
            if animated_url:
                filename = f"highlight_{idx}_2_animated.mp4"
                path = videos_dir / filename
                if self.download_video(animated_url, path):
                    highlight_data["videos"].append(str(path))
            
            if highlight_data["videos"]:
                processed.append(highlight_data)
        
        # Save metadata
        if processed:
            meta_path = output_dir / "metadata.json"
            with open(meta_path, "w") as f:
                json.dump({
                    "game_pk": game_pk,
                    "date": date_str,
                    "team_id": self.team_id,
                    "highlights": processed
                }, f, indent=2)
            
            print(f"\n✅ Processed {len(processed)} highlights")
            print(f"📁 Output directory: {output_dir}")
        
        return processed

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract clips from MLB games")
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
    clips = MLBGameClips(game_date, args.team)
    
    print(f"🎯 Looking for game on {clips.date}")
    game = clips.get_game()
    
    if not game:
        print("❌ No game found for specified date and team")
        return
        
    game_pk = game.get("gamePk")
    if not game_pk:
        print("❌ Invalid game data")
        return
    
    print(f"🎮 Processing game {game_pk}")
    highlights = clips.process_highlights(game_pk)
    
    # Open output directory if requested
    if args.open and highlights:
        date_str = clips.date.strftime("%Y-%m-%d")
        output_dir = clips.output_dir / f"{date_str}_{clips.team_id}"
        if os.path.exists(output_dir):
            subprocess.run(["open", str(output_dir)])

if __name__ == "__main__":
    main()