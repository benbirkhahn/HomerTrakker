#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

def process_clip(input_path, output_path):
    """Process clip with FFmpeg for optimal quality"""
    try:
        # High quality encoding settings
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-preset', 'veryslow',  # Best quality encoding
            '-crf', '18',  # High quality (lower = better, range 0-51)
            '-vf', 'scale=1920:1080:flags=lanczos',  # Upscale to 1080p with high quality scaler
            '-maxrate', '8M', '-bufsize', '16M',  # High bitrate constraints
            '-profile:v', 'high',  # High profile for better quality
            '-pix_fmt', 'yuv420p',  # Standard pixel format for compatibility
            '-movflags', '+faststart',  # Web playback optimization
            '-c:a', 'aac', '-b:a', '192k',  # High quality audio
            output_path
        ]
        
        print(f"\n🎬 Processing {Path(input_path).name}...")
        subprocess.run(cmd, check=True)
        print(f"✅ Processed: {Path(output_path).name}")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error: {e}")
    except Exception as e:
        print(f"❌ Error processing clip: {e}")

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2025-10-01"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Input/output directories
    input_dir = os.path.join(base_dir, "MLB_HomeRun_Posts", date_str, "videos")
    output_dir = os.path.join(base_dir, "MLB_HomeRun_Posts", date_str, "processed")
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n🎬 HIGH QUALITY CLIP PROCESSOR")
    print("=" * 35)
    
    # Process all MP4 files in input directory
    for file in os.listdir(input_dir):
        if file.endswith('.mp4'):
            input_path = os.path.join(input_dir, file)
            output_path = os.path.join(output_dir, f"hq_{file}")
            
            if os.path.exists(output_path):
                print(f"⏭️  Already exists: {os.path.basename(output_path)}")
            else:
                process_clip(input_path, output_path)
    
    print("\n✨ Processing complete!")

if __name__ == "__main__":
    main()