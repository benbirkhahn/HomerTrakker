#!/bin/zsh
source /Users/benbirkhahn/twitter_bot_env/bin/activate
pip install -r requirements-monitor.txt
python3 homer_monitor_dashboard.py