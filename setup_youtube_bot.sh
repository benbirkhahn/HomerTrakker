#!/bin/bash
# YouTube API Setup Script - Much easier than Twitter and 100% FREE!

echo "🎬 YOUTUBE API SETUP GUIDE 🎬"
echo "============================="
echo ""
echo "💰 100% FREE with generous quotas (10,000 requests/day)"
echo "⚡ Setup takes ~5 minutes (much easier than Instagram/Twitter)"
echo ""
echo "📋 Step-by-step setup:"
echo ""

echo "1️⃣  CREATE GOOGLE CLOUD PROJECT"
echo "   • Go to: https://console.developers.google.com/"
echo "   • Click 'New Project' or select existing project"
echo "   • Project name: 'MLB Home Run Bot'"
echo "   • Click 'Create'"
echo ""

echo "2️⃣  ENABLE YOUTUBE DATA API"
echo "   • In your project dashboard"
echo "   • Click 'Enable APIs and Services'"
echo "   • Search for 'YouTube Data API v3'"
echo "   • Click it and press 'Enable'"
echo ""

echo "3️⃣  CREATE OAUTH 2.0 CREDENTIALS"
echo "   • Go to 'Credentials' in left sidebar"
echo "   • Click 'Create Credentials' → 'OAuth 2.0 Client IDs'"
echo "   • Application type: 'Desktop application'"
echo "   • Name: 'MLB Home Run Bot'"
echo "   • Click 'Create'"
echo ""

echo "4️⃣  DOWNLOAD CREDENTIALS FILE"
echo "   • After creating, click the download icon (⬇️)"
echo "   • Save the JSON file in this directory"
echo "   • Rename it to: 'youtube_credentials.json'"
echo ""

echo "5️⃣  TEST THE BOT"
echo "   • Run: python3 youtube_homer_bot.py"
echo "   • First time will open browser for authorization"
echo "   • Click 'Allow' to grant permissions"
echo "   • Done! Bot is now ready for automation"
echo ""

echo "🚀 AFTER SETUP - FULL AUTOMATION!"
echo "================================"
echo "Your complete pipeline will be:"
echo "1. Detect MLB home runs → live_mlb_homer_detector.py"
echo "2. Download video highlights → download_homer_videos.py"
echo "3. Compile multi-angle videos → simple_video_compiler.py"
echo "4. Upload to YouTube automatically → youtube_homer_bot.py"
echo ""

echo "📊 YOUTUBE API QUOTAS (FREE TIER)"
echo "================================="
echo "• 10,000 requests per day (very generous)"
echo "• Each video upload = ~1,600 quota units"
echo "• You can upload ~6 videos per day for FREE"
echo "• Perfect for daily MLB home runs!"
echo ""

echo "💡 PRO TIPS"
echo "==========="
echo "• YouTube Shorts (≤60s) get more visibility"
echo "• Use good titles with player names for SEO"
echo "• Upload consistently for better algorithm performance"
echo "• Sports content does very well on YouTube"
echo ""

echo "🔒 SECURITY NOTES"
echo "================="
echo "• OAuth tokens stored locally in 'youtube_token.json'"
echo "• Never share your credentials file publicly"
echo "• Tokens refresh automatically (no maintenance needed)"
echo ""

# Ask if they want to open the Google Cloud Console
read -p "🌐 Open Google Cloud Console now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "https://console.developers.google.com/"
fi

echo ""
echo "✨ Happy home run uploading! ⚾🎬"