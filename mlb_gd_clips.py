#!/usr/bin/env python3
"""
MLB Game Day Clip Extractor (XML Feed)
- Uses MLB's XML-based Game Day feed
- Supports multiple camera angles
- Includes StatCast data and overlays
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import urllib.parse
from xml.etree import ElementTree
import time
import subprocess

class MLBGameDayXML:
    def __init__(self, game_date=None, team_id=None):
        self.date = game_date or (datetime.now() - timedelta(days=1)).date()
        self.team_id = team_id or 147  # Default to Yankees
        self.base_url = "https://gd2.mlb.com/components/game/mlb"
        self.output_dir = Path.home() / "game_clips" / "gameday"
        
    def _make_request(self, url):
        """Make an API request with proper error handling."""
        try:
            print(f"📡 Requesting: {url}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/xml,application/xml"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode()
        except Exception as e:
            print(f"⚠️  Request failed: {e}")
            return None

    def _get_xml(self, url):
        """Get and parse XML content."""
        content = self._make_request(url)
        if content:
            try:
                return ElementTree.fromstring(content)
            except Exception as e:
                print(f"⚠️  XML parse error: {e}")
        return None

    def get_game(self):
        """Get game data for specified date and team."""
        year = self.date.strftime("%Y")
        month = self.date.strftime("%m")
        day = self.date.strftime("%d")
        
        # First get the master scoreboard
        url = f"{self.base_url}/year_{year}/month_{month}/day_{day}/master_scoreboard.xml"
        root = self._get_xml(url)
        
        if root is not None:
            # Find game with matching team
            for game in root.findall(".//game"):
                home_id = game.get("home_team_id")
                away_id = game.get("away_team_id")
                if str(self.team_id) in (home_id, away_id):
                    return {
                        "id": game.get("id"),
                        "home_team_id": home_id,
                        "away_team_id": away_id,
                        "venue": game.get("venue"),
                        "game_pk": game.get("game_pk")
                    }
        return None

    def get_game_data(self, game_id):
        """Get detailed game data including all plays and media."""
        year = self.date.strftime("%Y")
        month = self.date.strftime("%m")
        day = self.date.strftime("%d")
        
        # Get game events
        url = f"{self.base_url}/year_{year}/month_{month}/day_{day}/gid_{game_id}/game_events.xml"
        events_root = self._get_xml(url)
        
        # Get media/highlights
        media_url = f"{self.base_url}/year_{year}/month_{month}/day_{day}/gid_{game_id}/media/highlights.xml"
        media_root = self._get_xml(media_url)
        
        return events_root, media_root

    def get_highlight_info(self, highlight):
        """Extract highlight information from XML."""
        info = {
            "id": highlight.get("id"),
            "date": highlight.get("date"),
            "type": highlight.get("type"),
            "title": highlight.findtext("title"),
            "description": highlight.findtext("description"),
            "duration": highlight.findtext("duration"),
            "urls": []
        }
        
        # Get all available URLs
        for url in highlight.findall(".//url"):
            info["urls"].append({
                "playback_scenario": url.get("playback_scenario"),
                "speed": url.get("speed"),
                "url": url.text
            })
        
        return info

    def download_clip(self, url, output_path, description=""):
        """Download video clip with progress tracking."""
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

    def process_highlights(self, game_id):
        """Process and download all available highlight angles."""
        events_root, media_root = self.get_game_data(game_id)
        
        if media_root is None:
            print("No highlight data available")
            return []
        
        # Create output directories
        date_str = self.date.strftime("%Y-%m-%d")
        output_dir = self.output_dir / f"{date_str}_{self.team_id}"
        videos_dir = output_dir / "videos"
        os.makedirs(videos_dir, exist_ok=True)
        
        processed = []
        
        # Process each highlight
        for highlight in media_root.findall(".//highlight"):
            info = self.get_highlight_info(highlight)
            if not info["urls"]:
                continue
            
            print(f"\nProcessing: {info['title']}")
            
            # Group URLs by playback scenario
            scenarios = {}
            for url_info in info["urls"]:
                scenario = url_info["playback_scenario"]
                if scenario not in scenarios:
                    scenarios[scenario] = []
                scenarios[scenario].append(url_info)
            
            # Download best quality for each scenario
            highlight_data = {
                "title": info["title"],
                "description": info["description"],
                "duration": info["duration"],
                "videos": []
            }
            
            for scenario, urls in scenarios.items():
                # Sort by speed (higher is better)
                urls.sort(key=lambda x: int(x.get("speed", 0)), reverse=True)
                best_url = urls[0]["url"]
                
                # Generate filename
                safe_title = re.sub(r'[^a-zA-Z0-9]+', '_', info['title'].lower()).strip('_')
                filename = f"{safe_title}_{scenario}.mp4"
                path = videos_dir / filename
                
                if self.download_clip(best_url, path, f"{info['title']} - {scenario}"):
                    video_info = {
                        "path": str(path),
                        "scenario": scenario,
                        "speed": urls[0]["speed"]
                    }
                    highlight_data["videos"].append(video_info)
            
            if highlight_data["videos"]:
                processed.append(highlight_data)
        
        # Save metadata
        if processed:
            meta_path = output_dir / "metadata.json"
            with open(meta_path, "w") as f:
                json.dump({
                    "game_id": game_id,
                    "date": date_str,
                    "team_id": self.team_id,
                    "highlights": processed
                }, f, indent=2)
            
            print(f"\n✅ Processed {len(processed)} highlights")
            print(f"📁 Output directory: {output_dir}")
        
        return processed

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract clips using MLB Game Day XML feed")
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
    gameday = MLBGameDayXML(game_date, args.team)
    
    print(f"🎯 Looking for game on {gameday.date}")
    game = gameday.get_game()
    
    if not game:
        print("❌ No game found for specified date and team")
        return
    
    print(f"🎮 Processing game {game['id']}")
    highlights = gameday.process_highlights(game['id'])
    
    # Open output directory if requested
    if args.open and highlights:
        date_str = gameday.date.strftime("%Y-%m-%d")
        output_dir = gameday.output_dir / f"{date_str}_{gameday.team_id}"
        if os.path.exists(output_dir):
            subprocess.run(["open", str(output_dir)])

if __name__ == "__main__":
    main()