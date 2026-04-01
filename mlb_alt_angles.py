#!/usr/bin/env python3
"""
MLB Alternative Angles Extractor
- Focuses on alternative camera angles and high-resolution clips
- Uses MLB's enhanced content feed
- Includes StatCast and specialized camera angles
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

class MLBAltAngles:
    def __init__(self, game_date=None, team_id=None):
        self.date = game_date or (datetime.now() - timedelta(days=1)).date()
        self.team_id = team_id or 147  # Default to Yankees
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.output_dir = Path.home() / "game_clips" / "alt_angles"
        
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
            "hydrate": "team,content(highlights,media)"
        }
        data = self._make_request(f"{self.base_url}/schedule", params)
        
        for date in data.get("dates", []):
            for game in date.get("games", []):
                return game
        return None

    def get_content(self, game_pk):
        """Get enhanced content feed with all available angles."""
        return self._make_request(f"{self.base_url}/game/{game_pk}/content")

    def get_statcast(self, game_pk):
        """Get StatCast data with enhanced visualizations."""
        params = {
            "game_pk": game_pk,
            "type": "statcast"
        }
        return self._make_request(f"{self.base_url}/game/{game_pk}/feed/live", params)

    def pick_best_quality(self, playbacks):
        """Select the highest quality version from available playbacks."""
        quality_order = ["4K", "2160p", "4000K", "1080p", "720p"]
        url_by_quality = {}
        
        for pb in playbacks:
            url = pb.get("url", "")
            if not url or not url.endswith(".mp4"):
                continue
                
            # Check quality and resolution
            for quality in quality_order:
                if quality in url:
                    url_by_quality[quality] = url
                    break
            
            # Also check for high bitrate versions
            if "high" in pb.get("name", "").lower():
                url_by_quality["high"] = url
        
        # Return highest available quality
        for quality in quality_order:
            if quality in url_by_quality:
                return url_by_quality[quality]
        
        return url_by_quality.get("high") or next(iter(url_by_quality.values())) if url_by_quality else None

    def download_video(self, url, output_path, description=""):
        """Download a video file with progress tracking."""
        try:
            print(f"📥 Downloading: {description}")
            headers = {"User-Agent": "Mozilla/5.0"}
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

    def process_content(self, game_pk):
        """Process and download alternative angles from game content."""
        content = self.get_content(game_pk)
        
        # Get different types of content
        highlights = (content.get("highlights", {}) or {}).get("highlights", {}).get("items", [])
        alt_angles = (content.get("media", {}) or {}).get("alternateAngles", [])
        iso_angles = (content.get("media", {}) or {}).get("isolatedAngles", [])
        statcast = (content.get("media", {}) or {}).get("statcast", [])
        
        if not any([highlights, alt_angles, iso_angles, statcast]):
            print("No alternative angles found")
            return []
        
        # Create output directories
        date_str = self.date.strftime("%Y-%m-%d")
        output_dir = self.output_dir / f"{date_str}_{self.team_id}"
        videos_dir = output_dir / "videos"
        os.makedirs(videos_dir, exist_ok=True)
        
        processed = []
        
        # Process regular highlights with multiple angles
        for idx, item in enumerate(highlights, 1):
            if not item.get("playbacks"):
                continue
                
            title = item.get("title", "").strip()
            if not title:
                continue
            
            print(f"\nProcessing highlight {idx}: {title}")
            
            # Organize playbacks by view type
            views = {}
            for pb in item.get("playbacks", []):
                view_type = pb.get("type", "default")
                if view_type not in views:
                    views[view_type] = []
                views[view_type].append(pb)
            
            # Only process if we have multiple angles
            if len(views) <= 1:
                continue
            
            highlight_data = {
                "title": title,
                "blurb": item.get("blurb"),
                "description": item.get("description"),
                "duration": item.get("duration"),
                "videos": []
            }
            
            # Download each unique view
            for view_type, playbacks in views.items():
                best_url = self.pick_best_quality(playbacks)
                if not best_url:
                    continue
                
                # Create safe filename
                safe_title = re.sub(r'[^a-zA-Z0-9]+', '_', title.lower()).strip('_')
                filename = f"highlight_{idx}_{view_type}_{safe_title}.mp4"
                path = videos_dir / filename
                
                if self.download_video(best_url, path, f"{title} - {view_type} angle"):
                    video_info = {
                        "path": str(path),
                        "type": view_type,
                        "title": title
                    }
                    highlight_data["videos"].append(video_info)
            
            if highlight_data["videos"]:
                processed.append(highlight_data)
        
        # Process isolated angles and alternative views
        for idx, item in enumerate(alt_angles + iso_angles + statcast, len(processed) + 1):
            if not item.get("playbacks"):
                continue
                
            title = item.get("title", "").strip()
            if not title:
                continue
            
            print(f"\nProcessing alternative angle {idx}: {title}")
            
            best_url = self.pick_best_quality(item.get("playbacks", []))
            if not best_url:
                continue
            
            # Create safe filename
            safe_title = re.sub(r'[^a-zA-Z0-9]+', '_', title.lower()).strip('_')
            filename = f"alt_angle_{idx}_{safe_title}.mp4"
            path = videos_dir / filename
            
            if self.download_video(best_url, path, title):
                alt_data = {
                    "title": title,
                    "description": item.get("description"),
                    "videos": [{
                        "path": str(path),
                        "type": "alternative",
                        "title": title
                    }]
                }
                processed.append(alt_data)
        
        # Save metadata
        if processed:
            meta_path = output_dir / "metadata.json"
            with open(meta_path, "w") as f:
                json.dump({
                    "game_pk": game_pk,
                    "date": date_str,
                    "team_id": self.team_id,
                    "content": processed
                }, f, indent=2)
            
            print(f"\n✅ Processed {len(processed)} items with alternative angles")
            print(f"📁 Output directory: {output_dir}")
        
        return processed

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract alternative angles from MLB game content")
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
    alt_angles = MLBAltAngles(game_date, args.team)
    
    print(f"🎯 Looking for game on {alt_angles.date}")
    game = alt_angles.get_game()
    
    if not game:
        print("❌ No game found for specified date and team")
        return
    
    game_pk = game.get("gamePk")
    if not game_pk:
        print("❌ Invalid game data")
        return
    
    print(f"🎮 Processing game {game_pk}")
    highlights = alt_angles.process_content(game_pk)
    
    # Open output directory if requested
    if args.open and highlights:
        date_str = alt_angles.date.strftime("%Y-%m-%d")
        output_dir = alt_angles.output_dir / f"{date_str}_{alt_angles.team_id}"
        if os.path.exists(output_dir):
            subprocess.run(["open", str(output_dir)])

if __name__ == "__main__":
    main()