#!/usr/bin/env python3
"""Check staged backup files. Reports locations/rules, never matched secret values."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
RULES={
    'oauth_client_secret':r'GOCSPX-[A-Za-z0-9_-]+',
    'google_access_token':r'ya29\.[A-Za-z0-9._-]+',
    'github_token':r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})',
    'aws_access_key':r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'credential_json_value':r'"(?:client_secret|refresh_token|access_token)"\s*:\s*"(?!<|your_|example)[^"\n]{12,}"',
    'bearer_literal':r'(?i)Bearer\s+[A-Za-z0-9._-]{24,}',
    'contact_phone':r'\+[1-9]\d{9,14}\b',
}
FORBIDDEN=re.compile(r'(^|/)(?:MLB_HomeRun_Posts|Shorts_Ready|YouTube_Shorts_Ready|Thumbnails_Ready|logs|\.homer|\.n8n|\.homer_cache|twitter_bot_env|\.venv|backup-private)(?:/|$)|(?:^|/)(?:youtube_token|youtube_credentials|client_secret[^/]*|state|uploads|youtube_queue[^/]*)\.json$|\.(?:mp4|mov|mkv|sqlite|db|log|pem|key|pyc|bak)$|(?:^|/)\.homer\.env$')

def scan():
    paths=[p for p in subprocess.check_output(['git','ls-files','--cached','-z'],cwd=ROOT).decode().split('\0') if p]
    findings=[]
    for name in paths:
        if FORBIDDEN.search(name):findings.append({'path':name,'rule':'private_or_runtime_path'});continue
        p=ROOT/name
        if not p.is_file():continue # deletions contain no newly published bytes
        text=p.read_text(errors='replace')
        for rule,pattern in RULES.items():
            for m in re.finditer(pattern,text):findings.append({'path':name,'line':text.count('\n',0,m.start())+1,'rule':rule})
    return {'filesScanned':len(paths),'findings':findings,'method':'known credential signatures, JSON values, contact literals and forbidden paths; not a proof against every possible secret'}

if __name__=='__main__':
    result=scan();print(json.dumps(result,indent=2));sys.exit(bool(result['findings']))
