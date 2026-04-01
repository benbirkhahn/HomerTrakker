#!/usr/bin/env python3
"""
MLB Film Room Clip Extractor
- Focuses on alternative angles and high-resolution clips
- Uses MLB Film Room's enhanced feed
- Supports multiple camera angles per play
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

class MLBFilmRoom:
    def __init__(self, game_date=None, team_id=None):
        self.date = game_date or (datetime.now() - timedelta(days=1)).date()
        self.team_id = team_id or 147  # Default to Yankees
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.film_room_url = "https://www.mlb.com/video/search/api"
        self.output_dir = Path.home() / "game_clips" / "film_room"
        
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
                "Referer": "https://www.mlb.com/video",
                "Origin": "https://www.mlb.com"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"⚠️  Request failed: {e}")
            return {}

    def get_game_pk(self):
        """Get game ID for the specified date and team."""
        params = {
            "sportId": 1,
            "date": self.date.strftime("%Y-%m-%d"),
            "teamId": self.team_id,
            "hydrate": "team"
        }
        data = self._make_request(f"{self.base_url}/schedule", params)
        
        for date in data.get("dates", []):
            for game in date.get("games", []):
                return game.get("gamePk")
        return None

    def search_film_room(self, game_pk):
        """Search Film Room for all available angles of game highlights."""
        params = {
            "q": f"GamePk = {game_pk}",
            "qt": "game",
            "p": 1,
            "ps": 100,
            "sort": "timestamp,desc",
            "sortOrder": "desc",
            "type": "video"
        }
        return self._make_request(self.film_room_url, params)

    def get_highest_quality_url(self, playback_urls):
        """Select the highest quality version from available playback URLs."""
        quality_order = ["4K", "2160p", "4000K", "1080p", "720p"]
        
        # First try to find highest resolution
        for quality in quality_order:
            for url in playback_urls:
                if quality in url:
                    return url
        
        # If no preferred quality found, return the URL with highest bitrate
        max_bitrate = 0
        best_url = None
        for url in playback_urls:
            match = re.search(r'(\d+)K', url)
            if match:
                bitrate = int(match.group(1))
                if bitrate > max_bitrate:
                    max_bitrate = bitrate
                    best_url = url
        
        return best_url or playback_urls[0] if playback_urls else None

    def download_video(self, url, output_path, title=""):
        """Download a video file with progress indicator."""
        try:
            print(f"📥 Downloading: {title}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.mlb.com/video"
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
                        
                        # Calculate progress
                        if total_size > 0:
                            progress = (current_size / total_size) * 100
                            print(f"\rProgress: {progress:.1f}% ({current_size}/{total_size} bytes)", end="")
                
                print(f"\n✅ Downloaded: {output_path}")
                return True
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

    def process_highlights(self, game_pk):
        """Process and download all available angles for game highlights."""
        search_results = self.search_film_room(game_pk)
        highlights = search_results.get("docs", [])
        
        if not highlights:
            print("No highlights found in Film Room")
            return []
        
        # Create output directories
        date_str = self.date.strftime("%Y-%m-%d")
        output_dir = self.output_dir / f"{date_str}_{self.team_id}"
        videos_dir = output_dir / "videos"
        os.makedirs(videos_dir, exist_ok=True)
        
        processed = []
        for idx, item in enumerate(highlights, 1):
            title = item.get("title", "")
            if not title:
                continue
                
            print(f"\nProcessing highlight {idx}: {title}")
            
            # Get all available angles
            angles = item.get("playbacks", [])
            if not angles:
                print("No video angles found")
                continue
            
            # Process each unique angle
            highlight_data = {
                "title": title,
                "timestamp": item.get("timestamp"),
                "description": item.get("description"),
                "keywords": item.get("keywords", []),
                "videos": []
            }
            
            # Group angles by type
            angle_groups = {}
            for angle in angles:
                angle_type = angle.get("type", "default")
                if angle_type not in angle_groups:
                    angle_groups[angle_type] = []
                angle_groups[angle_type].append(angle)
            
            # Download best quality for each angle type
            for angle_type, angle_list in angle_groups.items():
                # Get URLs for this angle type
                urls = [a.get("url") for a in angle_list if a.get("url")]
                if not urls:
                    continue
                
                # Get highest quality URL
                best_url = self.get_highest_quality_url(urls)
                if not best_url:
                    continue
                
                # Generate filename
                safe_title = re.sub(r'[^a-zA-Z0-9]+', '_', title.lower()).strip('_')
                filename = f"highlight_{idx}_{angle_type}_{safe_title}.mp4"
                path = videos_dir / filename
                
                # Download video
                if self.download_video(best_url, path, title):
                    video_info = {
                        "path": str(path),
                        "angle_type": angle_type,
                        "quality": "unknown"
                    }
                    
                    # Try to determine quality
                    for quality in ["4K", "2160p", "4000K", "1080p", "720p"]:
                        if quality in best_url:
                            video_info["quality"] = quality
                            break
                    
                    highlight_data["videos"].append(video_info)
            
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
    
    parser = argparse.ArgumentParser(description="Extract alternative angles from MLB Film Room")
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
    film_room = MLBFilmRoom(game_date, args.team)
    
    print(f"🎯 Looking for game on {film_room.date}")
    game_pk = film_room.get_game_pk()
    
    if not game_pk:
        print("❌ No game found for specified date and team")
        return
    
    print(f"🎮 Processing game {game_pk}")
    highlights = film_room.process_highlights(game_pk)
    
    # Open output directory if requested
    if args.open and highlights:
        date_str = film_room.date.strftime("%Y-%m-%d")
        output_dir = film_room.output_dir / f"{date_str}_{film_room.team_id}"
        if os.path.exists(output_dir):
            subprocess.run(["open", str(output_dir)])

if __name__ == "__main__":
    main()