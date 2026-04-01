#!/usr/bin/env python3
import json
import requests
import sys
import os
from datetime import datetime

def get_game_content(date_str):
    # MLB Stats API endpoint for game content
    game_pk = "813070"  # Hardcoded for Ben Rice's game
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/content"
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'highlights' in data and 'highlights' in data['highlights']:
            items = data['highlights']['highlights']['items']
            clips = []
            
            for item in items:
                if 'Ben Rice' in item.get('headline', '') and 'home run' in item.get('headline', '').lower():
                    # Get all available playback formats
                    playbacks = sorted(item['playbacks'], 
                                    key=lambda x: (x.get('width', 0), x.get('height', 0)), 
                                    reverse=True)
                    
                    if playbacks:
                        best_quality = playbacks[0]
                        clips.append({
                            'title': item.get('headline', ''),
                            'description': item.get('description', ''),
                            'date': item.get('date', ''),
                            'duration': item.get('duration', ''),
                            'playbacks': [{
                                'url': p['url'],
                                'width': p.get('width', 'N/A'),
                                'height': p.get('height', 'N/A'),
                                'name': p.get('name', 'N/A')
                            } for p in playbacks]
                        })
            
            return clips
            
    except Exception as e:
        print(f"Error fetching clips: {str(e)}")
        return None

def download_clip(url, output_dir, filename):
    """Download a clip to the specified directory"""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✅ Downloaded: {filename}")
        return output_path
    except Exception as e:
        print(f"❌ Failed to download {filename}: {str(e)}")
        return None

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2025-10-01"
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                             "MLB_HomeRun_Posts", date_str, "videos")
    
    clips = get_game_content(date_str)
    
    if clips:
        print(f"\nFound {len(clips)} clips from {date_str}:\n")
        
        for i, clip in enumerate(clips, 1):
            print(f"Clip #{i}:")
            print(f"Title: {clip['title']}")
            print(f"Description: {clip['description']}")
            print(f"Duration: {clip['duration']}")
            print("\nAvailable formats:")
            
            for j, playback in enumerate(clip['playbacks'], 1):
                print(f"\n  Format #{j}:")
                print(f"  Resolution: {playback['width']}x{playback['height']}")
                print(f"  Type: {playback['name']}")
                print(f"  URL: {playback['url']}")
                
                # Download highest quality versions
                if j == 1:  # Highest quality version
                    filename = f"homer_{i}_{j}_{playback['name'].lower()}.mp4"
                    download_clip(playback['url'], output_dir, filename)
            
            print("\n" + "="*50 + "\n")
    else:
        print(f"No clips found for {date_str}")

if __name__ == "__main__":
    main()