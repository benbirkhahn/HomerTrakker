#!/usr/bin/env python3
"""
Twitter Home Run Bot - Automatically posts MLB home runs to Twitter
Much easier than Instagram - full automation possible!
"""

import tweepy
import os
import glob
import time
import re
from datetime import datetime

class TwitterHomeRunBot:
    def __init__(self):
        """Initialize Twitter bot with API credentials"""
        # You'll need to set these environment variables
        self.consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
        self.consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET') 
        self.access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
        
        if not all([self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret]):
            print("❌ Missing Twitter API credentials!")
            print("📋 Setup instructions:")
            print("1. Go to https://developer.twitter.com")
            print("2. Create a new app")
            print("3. Get your API keys")
            print("4. Set environment variables:")
            print("   export TWITTER_CONSUMER_KEY='your_key'")
            print("   export TWITTER_CONSUMER_SECRET='your_secret'")
            print("   export TWITTER_ACCESS_TOKEN='your_token'")
            print("   export TWITTER_ACCESS_TOKEN_SECRET='your_token_secret'")
            return
        
        # Initialize Twitter API
        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        auth.set_access_token(self.access_token, self.access_token_secret)
        self.api = tweepy.API(auth, wait_on_rate_limit=True)
        
        print("✅ Twitter bot initialized successfully!")
    
    def extract_tweet_text(self, post_file):
        """Extract and format caption for Twitter (280 char limit)"""
        try:
            with open(post_file, 'r') as f:
                content = f.read()
            
            # Extract the main caption
            lines = content.split('\n')
            caption_lines = []
            in_caption = False
            
            for line in lines:
                if line.startswith('CAPTION:'):
                    in_caption = True
                    continue
                elif line.startswith('HASHTAGS:'):
                    break
                elif in_caption and line.strip():
                    caption_lines.append(line.strip())
            
            tweet_text = ' '.join(caption_lines)
            
            # Add hashtags for Twitter
            hashtags = " #MLB #HomeRun #Baseball ⚾️"
            
            # Keep under Twitter's 280 character limit
            max_length = 280 - len(hashtags) - 30  # Buffer for video link
            if len(tweet_text) > max_length:
                tweet_text = tweet_text[:max_length-3] + "..."
            
            return tweet_text + hashtags
            
        except Exception as e:
            print(f"❌ Error reading {post_file}: {e}")
            return "Amazing home run! ⚾️ #MLB #HomeRun #Baseball"
    
    def post_homer_video(self, video_path, post_file):
        """Post a single home run video to Twitter"""
        try:
            print(f"🐦 Posting to Twitter: {os.path.basename(video_path)}")
            
            # Get tweet text
            tweet_text = self.extract_tweet_text(post_file)
            print(f"📝 Tweet: {tweet_text}")
            
            # Upload video and post
            media = self.api.media_upload(video_path)
            tweet = self.api.update_status(
                status=tweet_text,
                media_ids=[media.media_id]
            )
            
            print(f"✅ Posted successfully! Tweet ID: {tweet.id}")
            print(f"🔗 URL: https://twitter.com/user/status/{tweet.id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to post {video_path}: {e}")
            return False
    
    def post_all_homers(self):
        """Post all home run videos from today"""
        today = datetime.now().strftime('%Y-%m-%d')
        videos_dir = f"MLB_HomeRun_Posts/{today}/videos"
        posts_dir = f"MLB_HomeRun_Posts/{today}"
        
        if not os.path.exists(videos_dir):
            print(f"❌ No videos folder found: {videos_dir}")
            return
        
        # Get all video files
        video_files = glob.glob(f"{videos_dir}/*.mp4")
        if not video_files:
            print("❌ No videos found to post!")
            return
        
        print(f"🎬 Found {len(video_files)} videos to post")
        posted_count = 0
        
        for video_path in sorted(video_files):
            # Find matching post file
            video_name = os.path.basename(video_path)
            homer_match = re.search(r'homer_(\d+)_', video_name)
            
            if homer_match:
                homer_num = homer_match.group(1)
                post_files = glob.glob(f"{posts_dir}/tonights_homer_{homer_num}_*.txt")
                
                if post_files:
                    post_file = post_files[0]
                    if self.post_homer_video(video_path, post_file):
                        posted_count += 1
                        time.sleep(5)  # Rate limiting - be nice to Twitter
                else:
                    print(f"⚠️  No matching post file for {video_name}")
        
        print(f"🎉 Posted {posted_count}/{len(video_files)} videos successfully!")
    
    def test_connection(self):
        """Test if Twitter API is working"""
        try:
            user = self.api.verify_credentials()
            print(f"✅ Connected as: @{user.screen_name}")
            return True
        except Exception as e:
            print(f"❌ Twitter API connection failed: {e}")
            return False

def main():
    print("🐦 TWITTER HOME RUN BOT 🐦")
    print("==========================")
    print("📤 Automatically post MLB home runs to Twitter")
    print("")
    
    # Initialize bot
    bot = TwitterHomeRunBot()
    
    if not hasattr(bot, 'api'):
        return
    
    # Test connection
    if not bot.test_connection():
        return
    
    print("")
    print("Choose an option:")
    print("1. Post all today's home runs")
    print("2. Test with a single video")
    print("3. Just test API connection")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        bot.post_all_homers()
    elif choice == "2":
        video_path = input("Enter video file path: ").strip()
        post_path = input("Enter post text file path: ").strip()
        if os.path.exists(video_path) and os.path.exists(post_path):
            bot.post_homer_video(video_path, post_path)
        else:
            print("❌ File not found!")
    elif choice == "3":
        print("✅ API connection test completed!")
    else:
        print("❌ Invalid choice!")

if __name__ == "__main__":
    main()