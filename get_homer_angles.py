#!/usr/bin/env python3
import json
import requests
import sys
import os
from datetime import datetime

def get_game_pk(date_str, team="NYY"):
    """Get game PK for a specific date and team"""
    url = f"https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "date": date_str,
        "teamId": 147,  # NYY team ID
    }
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get('dates') and data['dates'][0].get('games'):
            return str(data['dates'][0]['games'][0]['gamePk'])
    except Exception as e:
        print(f"Error fetching game PK: {str(e)}")
    return None

def get_game_content(date_str):
    game_pk = get_game_pk(date_str)
    if not game_pk:
        print("Could not find game PK for the specified date")
        return None
        
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/content"
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        clips = []
        
        # Check highlights
        if 'highlights' in data and 'highlights' in data['highlights']:
            items = data['highlights']['highlights']['items']
            
            for item in items:
                headline = item.get('headline', '').lower()
                keywords = item.get('keywordsAll', [])
                keyword_texts = [k.get('displayName', '').lower() for k in keywords]
                
                # Look for Ben Rice home runs
                if any('ben rice' in k for k in keyword_texts) and \
                   any('home run' in k for k in keyword_texts):
                    
                    # Get all available playback formats
                    playbacks = sorted(item['playbacks'], 
                                    key=lambda x: (x.get('width', 0), x.get('height', 0)), 
                                    reverse=True)
                    
                    if playbacks:
                        clips.append({
                            'title': item.get('headline', ''),
                            'description': item.get('description', ''),
                            'duration': item.get('duration', ''),
                            'date': item.get('date', ''),
                            'blurb': item.get('blurb', ''),
                            'playbacks': playbacks
                        })
        
        return clips
            
    except Exception as e:
        print(f"Error fetching clips: {str(e)}")
        return None

def download_clip(url, output_dir, filename):
    """Download a clip to the specified directory"""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    
    # Skip if file exists
    if os.path.exists(output_path):
        print(f"⏭️  Already exists: {filename}")
        return output_path
        
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        
        with open(output_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                print(f"📥 Downloading: {filename}")
                for chunk in response.iter_content(chunk_size=block_size):
                    f.write(chunk)
                    downloaded += len(chunk)
                
        print(f"✅ Downloaded: {filename}")
        return output_path
    except Exception as e:
        print(f"❌ Failed to download {filename}: {str(e)}")
        return None

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2025-10-01"
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                             "MLB_HomeRun_Posts", date_str, "videos")
    
    print("\n🎬 MLB HOME RUN ANGLE DOWNLOADER")
    print("=" * 35)
    
    clips = get_game_content(date_str)
    
    if clips:
        print(f"\n📄 Found {len(clips)} home run clips from {date_str}")
        
        for i, clip in enumerate(clips, 1):
            print(f"\n🏠 Processing Home Run #{i}")
            print(f"Title: {clip['title']}")
            print(f"Description: {clip['description']}")
            print(f"Duration: {clip['duration']}")
            
            broadcast_clip = None
            statcast_clip = None
            
            # Find broadcast and Statcast clips
            for playback in clip['playbacks']:
                if playback.get('name') in ['mp4Avc', 'FLASH_2500K_960x540']:
                    if 'statcast' in playback.get('url', '').lower():
                        statcast_clip = playback
                    else:
                        broadcast_clip = playback
            
            # Download both angles
            if broadcast_clip:
                filename = f"homer_{i}_broadcast.mp4"
                download_clip(broadcast_clip['url'], output_dir, filename)
            
            if statcast_clip:
                filename = f"homer_{i}_statcast.mp4"
                download_clip(statcast_clip['url'], output_dir, filename)
                
            print("\n" + "-"*50)
    else:
        print(f"No clips found for {date_str}")

if __name__ == "__main__":
    main()