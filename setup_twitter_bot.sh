#!/bin/bash
# Twitter Bot Setup Script - Makes getting API keys super easy!

echo "🐦 TWITTER API SETUP GUIDE 🐦"
echo "=============================="
echo ""
echo "📋 Step-by-step setup (takes ~10 minutes):"
echo ""

echo "1️⃣  CREATE TWITTER DEVELOPER ACCOUNT"
echo "   • Go to: https://developer.twitter.com"
echo "   • Click 'Sign up for a free account'"
echo "   • Answer basic questions about your use case"
echo "   • Say you're building a 'hobby bot for MLB highlights'"
echo ""

echo "2️⃣  CREATE A NEW APP"
echo "   • Click 'Create an app'"
echo "   • Name: 'MLB Home Run Bot'"
echo "   • Description: 'Posts MLB home run highlights automatically'"
echo "   • Use case: 'Making a bot'"
echo ""

echo "3️⃣  GET YOUR API KEYS"
echo "   • Go to your app dashboard"
echo "   • Click 'Keys and tokens' tab"
echo "   • Generate all 4 credentials:"
echo "     - API Key (Consumer Key)"
echo "     - API Secret (Consumer Secret)"  
echo "     - Access Token"
echo "     - Access Token Secret"
echo ""

echo "4️⃣  SET ENVIRONMENT VARIABLES"
echo "   Run these commands with YOUR keys:"
echo ""

# Create the export commands template
cat << 'EOF'
export TWITTER_CONSUMER_KEY="your_api_key_here"
export TWITTER_CONSUMER_SECRET="your_api_secret_here" 
export TWITTER_ACCESS_TOKEN="your_access_token_here"
export TWITTER_ACCESS_TOKEN_SECRET="your_access_token_secret_here"
EOF

echo ""
echo "5️⃣  SAVE TO YOUR SHELL PROFILE"
echo "   Add those export lines to your ~/.zshrc:"

cat << 'EOF'

# Add to ~/.zshrc to make permanent:
echo '
# Twitter Bot API Keys
export TWITTER_CONSUMER_KEY="your_api_key_here"
export TWITTER_CONSUMER_SECRET="your_api_secret_here"
export TWITTER_ACCESS_TOKEN="your_access_token_here" 
export TWITTER_ACCESS_TOKEN_SECRET="your_access_token_secret_here"
' >> ~/.zshrc

# Reload your shell:
source ~/.zshrc
EOF

echo ""
echo "6️⃣  TEST THE BOT"
echo "   Activate virtual environment and run:"
echo "   source twitter_bot_env/bin/activate"
echo "   python3 twitter_homer_bot.py"
echo ""

echo "🚀 AFTER SETUP - FULL AUTOMATION!"
echo "================================"
echo "Once working, you can:"
echo "• Run the MLB detector: python3 live_mlb_homer_detector.py"
echo "• Auto-post to Twitter: python3 twitter_homer_bot.py"
echo "• Set up cron job for full automation"
echo ""

echo "📞 NEED HELP?"
echo "============="
echo "If Twitter rejects your developer application:"
echo "• Be specific: 'I'm creating a hobby bot to share MLB highlights'"
echo "• Mention it's for personal use, not commercial"
echo "• Explain you'll respect rate limits and terms of service"
echo ""

# Ask if they want to open the Twitter developer site
read -p "🌐 Open Twitter Developer site now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "https://developer.twitter.com"
fi

echo ""
echo "✨ Happy home run posting! ⚾️"