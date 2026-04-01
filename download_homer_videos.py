#!/usr/bin/env python3
"""
Download Home Run Videos - Gets all video files for Instagram posting
Downloads the actual .mp4 files from the URLs in your home run posts
"""

import urllib.request
import os
import re
import fnmatch
import time
import subprocess
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

BASE_DIR = str(Path(__file__).resolve().parent)

def extract_video_urls_from_file(file_path):
    """Extract preferred video URLs from a home run post file.
    Policy: at most 1 diamond (prefer 4000K) + 1 darkroom. Produced optional via HOMER_ALLOW_PRODUCED."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        allow_produced = os.getenv('HOMER_ALLOW_PRODUCED') == '1'
        pattern = r'https?://(?:mlb-cuts-diamond\.mlb\.com|darkroom-clips\.mlb\.com' + (r'|bdata-producedclips\.mlb\.com' if allow_produced else '') + r')/[^\s\n]+\.mp4'
        all_urls = re.findall(pattern, content)
        if not all_urls:
            return []
        
        # Partition
        diamond = [u for u in all_urls if 'mlb-cuts-diamond.mlb.com' in u]
        darkroom = [u for u in all_urls if 'darkroom-clips.mlb.com' in u]
        produced = [u for u in all_urls if 'bdata-producedclips.mlb.com' in u]
        
        # Pick single diamond (prefer 4000K)
        def pick_single_diamond(urls):
            for u in urls:
                if '4000K' in u:
                    return u
            return urls[0] if urls else None
        d = pick_single_diamond(diamond)
        a = darkroom[0] if darkroom else None
        out = []
        if d:
            out.append(d)
        if a:
            out.append(a)
        if not out and allow_produced and produced:
            out.append(produced[0])
        return out
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

def download_video(url, filename):
    """Download a video file"""
    try:
        print(f"📥 Downloading: {filename}")
        
        # Create request with headers to avoid blocking
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        with urllib.request.urlopen(req) as response:
            with open(filename, 'wb') as f:
                f.write(response.read())
        
        print(f"✅ Downloaded: {filename}")
        return True
    except Exception as e:
        print(f"❌ Failed to download {filename}: {e}")
        return False

def check_missing_animated(post_file: str, videos_dir: str) -> bool:
    """Check if a post is missing its animated clip. Returns True if animated clip is missing."""
    try:
        urls = extract_video_urls_from_file(post_file)
        if not urls:
            return False
            
        # Count animations we expect vs have
        animated_expected = sum(1 for u in urls if 'darkroom-clips.mlb.com' in u)
        if not animated_expected:
            return False
            
        # Check if we have the animated file
        batter_match = re.search(r'tonights_homer_([0-9]+(?:-[0-9]+)?)_', os.path.basename(post_file))
        homer_num = batter_match.group(1) if batter_match else '0'
        
        animated_pattern = f"homer_{homer_num}_*_animated_*.mp4"
        animated_files = [f for f in os.listdir(videos_dir) if fnmatch.fnmatch(f, animated_pattern)]
        
        return len(animated_files) < animated_expected
    except Exception as e:
        print(f"Error checking for missing animated: {e}")
        return False

def retry_missing_animated(posts_dir: str, videos_dir: str, max_retries: int = 3, delay_mins: int = 2) -> None:
    """Retry downloading for posts missing their animated clips."""
    print("\n🔄 Checking for missing animated clips...")
    
    post_files = [f for f in os.listdir(posts_dir) if f.endswith('.txt')]
    missing_posts = [f for f in post_files if check_missing_animated(os.path.join(posts_dir, f), videos_dir)]
    
    if not missing_posts:
        print("✅ No posts missing animated clips")
        return
        
    print(f"⚠️  Found {len(missing_posts)} posts missing animated clips")
    
    for retry in range(max_retries):
        print(f"\n📥 Retry {retry + 1}/{max_retries} (waiting {delay_mins} mins)")
        time.sleep(delay_mins * 60)
        
        still_missing = []
        for post_file in missing_posts:
            file_path = os.path.join(posts_dir, post_file)
            print(f"\n🏠 Retrying {post_file}")
            
            urls = extract_video_urls_from_file(file_path)
            for url in urls:
                if 'darkroom-clips.mlb.com' not in url:
                    continue
                    
                parsed = urlparse(url)
                original_filename = os.path.basename(parsed.path)
                batter_match = re.search(r'tonights_homer_(\d+)_', post_file)
                homer_num = batter_match.group(1) if batter_match else '0'
                
                safe_filename = f"homer_{homer_num}_2_animated_{original_filename}"
                video_path = os.path.join(videos_dir, safe_filename)
                
                if os.path.exists(video_path):
                    print(f"   ⏭️  Already exists: {safe_filename}")
                    continue
                    
                if download_video(url, video_path):
                    print(f"   ✅ Downloaded missing animated clip: {safe_filename}")
                else:
                    still_missing.append(post_file)
                    
        missing_posts = still_missing
        if not missing_posts:
            print("\n✅ All missing animated clips retrieved!")
            return
            
    print(f"\n⚠️  {len(missing_posts)} posts still missing animated clips after {max_retries} retries")

def main():
    import sys, argparse, os, fnmatch, time
    print("🎬 MLB HOME RUN VIDEO DOWNLOADER 🎬")
    print("==================================")
    print("📥 Downloading all home run videos for Instagram posting")
    print("")
    
    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('date', nargs='?', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--open', dest='open_ui', action='store_true', help='Open videos folder when done')
    parser.add_argument('--retry-animated', dest='retry_animated', action='store_true', help='Retry downloading missing animated clips')
    parser.add_argument('--retry-count', type=int, default=3, help='Number of retries for missing animated clips')
    parser.add_argument('--retry-delay', type=int, default=2, help='Minutes to wait between retries')
    args = parser.parse_args()
    date_str = args.date
    posts_dir = os.path.join(BASE_DIR, "MLB_HomeRun_Posts", date_str)
    videos_dir = os.path.join(posts_dir, "videos")
    os.makedirs(videos_dir, exist_ok=True)
    
    # Get all home run post files
    if not os.path.exists(posts_dir):
        print(f"❌ Posts directory not found: {posts_dir}")
        return
    post_files = [f for f in os.listdir(posts_dir) if f.endswith('.txt')]
    
    if not post_files:
        print("❌ No home run post files found!")
        return
    
    print(f"📄 Found {len(post_files)} home run posts")
    print("")
    
    total_videos = 0
    downloaded = 0
    
    for i, post_file in enumerate(sorted(post_files), 1):
        file_path = os.path.join(posts_dir, post_file)
        
        # Extract batter name from filename for folder organization
        batter_match = re.search(r'tonights_homer_([0-9]+(?:-[0-9]+)?)_', post_file)
        homer_num = batter_match.group(1) if batter_match else str(i)
        
        print(f"🏠 Processing Home Run #{homer_num}")
        
        # Get video URLs from this post
        urls = extract_video_urls_from_file(file_path)
        
        if not urls:
            print(f"   📹 No videos found in {post_file}")
            continue
        
        # Count how many are animated
        animated_count = sum(1 for u in urls if 'darkroom-clips.mlb.com' in u)
        produced_count = sum(1 for u in urls if 'bdata-producedclips.mlb.com' in u)
        extra = []
        if animated_count:
            extra.append(f"{animated_count} animated")
        if produced_count:
            extra.append(f"{produced_count} produced")
        extra_str = (' including ' + ', '.join(extra)) if extra else ''
        print(f"   🎥 Found {len(urls)} video(s){extra_str}")
        
        # Download each video
        for j, url in enumerate(urls, 1):
            # Create filename, label animated replays
            parsed = urlparse(url)
            original_filename = os.path.basename(parsed.path)
            label = ''
            if 'darkroom-clips.mlb.com' in url:
                label = 'animated_'
            elif 'bdata-producedclips.mlb.com' in url:
                label = 'produced_'
            safe_filename = f"homer_{homer_num}_{j}_{label}{original_filename}"
            video_path = os.path.join(videos_dir, safe_filename)
            
            # Skip if already exists
            if os.path.exists(video_path):
                print(f"   ⏭️  Already exists: {safe_filename}")
                continue
            
            total_videos += 1
            if download_video(url, video_path):
                downloaded += 1
        
        print("")
    
    print("🎉 DOWNLOAD COMPLETE!")
    print("=" * 40)
    print(f"📊 Total videos processed: {total_videos}")
    print(f"✅ Successfully downloaded: {downloaded}")
    print(f"❌ Failed downloads: {total_videos - downloaded}")
    print("")
    print(f"📁 Videos saved to: {videos_dir}")
    print("")
    print("📱 TO USE WITH INSTAGRAM:")
    print("1. Open the videos folder")
    print("2. Select any .mp4 file")
    print("3. Upload to Instagram")
    print("4. Copy caption from the corresponding .txt file")
    print("")
    
    # Optionally open the videos folder (off by default for automation)
    # Retry missing animated clips if enabled (default: off)
    if args.retry_animated or os.getenv('HOMER_RETRY_ANIMATED') == '1':
        retry_missing_animated(posts_dir, videos_dir, args.retry_count, args.retry_delay)

    if args.open_ui or os.getenv('HOMER_OPEN_FOLDERS') == '1':
        print("🔍 Opening videos folder...")
        os.system(f'open "{videos_dir}"')

if __name__ == "__main__":
    main()