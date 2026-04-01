#!/usr/bin/env python3
import json
import requests
import sys
from datetime import datetime

def get_high_quality_clips(player_name, date_str):
    # MLB Film Room search API endpoint
    url = "https://www.mlb.com/data-service/en/search"
    
    # Format date for API
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    
    # Search parameters
    params = {
        "query": f"{player_name} home run",
        "page": "1",
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "hydrate": "game",
        "type": "video",
        "limit": "10",
        "offset": "0",
        "startDate": date_str,
        "endDate": date_str,
    }
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'docs' in data and data['docs']:
            clips = []
            for clip in data['docs']:
                if 'playbacks' in clip:
                    # Sort playbacks by width to get highest quality
                    playbacks = sorted(clip['playbacks'], 
                                    key=lambda x: (x.get('width', 0), x.get('height', 0)), 
                                    reverse=True)
                    
                    if playbacks:
                        best_quality = playbacks[0]
                        clips.append({
                            'title': clip.get('title', ''),
                            'description': clip.get('description', ''),
                            'date': clip.get('date', ''),
                            'url': best_quality.get('url', ''),
                            'width': best_quality.get('width', ''),
                            'height': best_quality.get('height', ''),
                            'bitrate': best_quality.get('bitrate', '')
                        })
            
            return clips
    except Exception as e:
        print(f"Error fetching clips: {str(e)}")
        return None

def main():
    if len(sys.argv) != 3:
        print("Usage: python get_high_quality.py 'Player Name' YYYY-MM-DD")
        sys.exit(1)
        
    player_name = sys.argv[1]
    date_str = sys.argv[2]
    
    clips = get_high_quality_clips(player_name, date_str)
    
    if clips:
        print(f"\nFound {len(clips)} clips for {player_name} on {date_str}:")
        for i, clip in enumerate(clips, 1):
            print(f"\nClip #{i}:")
            print(f"Title: {clip['title']}")
            print(f"Description: {clip['description']}")
            print(f"Quality: {clip['width']}x{clip['height']} @ {clip['bitrate']}kbps")
            print(f"URL: {clip['url']}")
    else:
        print(f"No clips found for {player_name} on {date_str}")

if __name__ == "__main__":
    main()