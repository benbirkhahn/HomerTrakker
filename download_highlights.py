#!/usr/bin/env python3
"""
Yankees Game Highlight Downloader
Downloads specific highlights from the Yankees vs Red Sox game (2025-10-01)
"""

import os
from pathlib import Path
import urllib.request

# Key highlights with their URLs
HIGHLIGHTS = {
    "wells_go_ahead": {
        "title": "Austin Wells' go-ahead single",
        "url": "https://mlb-cuts-diamond.mlb.com/FORGE/2025/2025-10/01/7140d9b8-6b92b224-779d1108-csvm-diamondgcp-asset_1280x720_59_4000K.mp4"
    },
    "rice_homer": {
        "title": "Ben Rice's two-run homer",
        "url": "https://mlb-cuts-diamond.mlb.com/FORGE/2025/2025-10/01/6b4b6663-96c674e2-13d84d4b-csvm-diamondgcp-asset_1280x720_59_4000K.mp4"
    },
    "story_homer": {
        "title": "Trevor Story's solo home run",
        "url": "https://mlb-cuts-diamond.mlb.com/FORGE/2025/2025-10/01/6b4b6663-96c674e2-13d84d4b-csvm-diamondgcp-asset_1280x720_59_16000K.mp4"
    },
    "judge_rbi": {
        "title": "Aaron Judge's RBI single",
        "url": "https://mlb-cuts-diamond.mlb.com/FORGE/2025/2025-10/01/7140d9b8-6b92b224-779d1108-csvm-diamondgcp-asset.m3u8"
    }
}

def download_highlight(url, output_path, title):
    """Download a video highlight."""
    try:
        print(f"📥 Downloading: {title}")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.mlb.com/"
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

def main():
    # Create output directory
    output_dir = Path.home() / "game_clips" / "2025-10-01_NYY" / "highlights"
    os.makedirs(output_dir, exist_ok=True)
    
    print("🎬 Downloading Yankees vs Red Sox Game 2 Highlights")
    print("=" * 50)
    
    # Download each highlight
    for key, info in HIGHLIGHTS.items():
        output_path = output_dir / f"{key}.mp4"
        if output_path.exists():
            print(f"⏭️  Skipping (already exists): {info['title']}")
            continue
        
        download_highlight(info['url'], output_path, info['title'])
    
    print("\n✅ Downloads complete!")
    print(f"📁 Highlights saved to: {output_dir}")
    
    # Open the output directory
    os.system(f'open "{output_dir}"')

if __name__ == "__main__":
    main()