#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
Statcast Enricher
Reads home run post files and enriches them with Statcast data (exit velocity, launch angle, distance)
using the MLB Stats API, then writes JSON files the YouTube bot can use.
"""

import os
import re
import json
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

API_BASE = "https://statsapi.mlb.com/api/v1"
BASE_DIR = str(Path(__file__).resolve().parent)

class StatcastEnricher:
    def __init__(self, date_str=None):
        self.today = date_str or datetime.now().strftime('%Y-%m-%d')
        self.posts_dir = os.path.join(BASE_DIR, "MLB_HomeRun_Posts", self.today)
        self.output_dir = os.path.join(self.posts_dir, "stats")
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"📅 Date: {self.today}")

    def _http_get_json(self, url, params=None):
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode('utf-8'))

    def _parse_post_file(self, path):
        info = {
            'batter': None,
            'batter_id': None,
            'game_str': None, # "Away @ Home"
            'game_pk': None,
            'inning_half': None, # top/bottom
            'inning_num': None,
            'pitcher': None
        }
        with open(path, 'r') as f:
            text = f.read()

        # Prefer structured fields first
        m = re.search(r"^GamePk:\s*(\d+)", text, flags=re.MULTILINE)
        if m:
            info['game_pk'] = int(m.group(1))
        m = re.search(r"^BatterId:\s*(\d+)", text, flags=re.MULTILINE)
        if m:
            info['batter_id'] = int(m.group(1))

        # Batter from HOME RUN DATA section or caption lines
        m = re.search(r"Batter:\s*(.+)", text)
        if m:
            info['batter'] = m.group(1).strip()
        else:
            # Try from caption lines '🔥 Name'
            m = re.search(r"^\s*🔥\s*([^\n]+)$", text, flags=re.MULTILINE)
            if m:
                info['batter'] = m.group(1).strip()

        # Game line like "Game: Cleveland Guardians @ Detroit Tigers"
        m = re.search(r"Game:\s*(.+@.+)", text)
        if m:
            info['game_str'] = m.group(1).strip()

        # Inning line like "Inning: top 4"
        m = re.search(r"Inning:\s*(top|bottom)\s*(\d+)", text, flags=re.IGNORECASE)
        if m:
            info['inning_half'] = m.group(1).lower()
            info['inning_num'] = int(m.group(2))

        # Pitcher from caption line 'vs Pitcher'
        m = re.search(r"^\s*⚾\s*vs\s+(.+)$", text, flags=re.MULTILINE)
        if m:
            info['pitcher'] = m.group(1).strip()

        return info

    def _find_game_pk(self, away_team, home_team):
        # Fetch schedule for the date
        data = self._http_get_json(f"{API_BASE}/schedule", {
            'sportId': 1,
            'date': self.today
        })
        for date in data.get('dates', []):
            for game in date.get('games', []):
                a = game.get('teams', {}).get('away', {}).get('team', {}).get('name')
                h = game.get('teams', {}).get('home', {}).get('team', {}).get('name')
                if not a or not h:
                    continue
                if a.lower() == away_team.lower() and h.lower() == home_team.lower():
                    return game.get('gamePk')
        return None

    def _safe_match_name(self, a, b):
        if not a or not b:
            return False
        return re.sub(r"[^a-z]", "", a.lower()) == re.sub(r"[^a-z]", "", b.lower())

    def _extract_statcast_from_play(self, play):
        # Find hitData inside playEvents
        hit = None
        for ev in play.get('playEvents', []):
            if 'hitData' in ev:
                hit = ev['hitData']
        if not hit and 'hitData' in play:
            hit = play['hitData']
        if not hit:
            return None
        return {
            'launchSpeed': hit.get('launchSpeed'),
            'launchAngle': hit.get('launchAngle'),
            'totalDistance': hit.get('totalDistance'),
            'trajectory': hit.get('trajectory'),
            'coordinates': hit.get('coordinates')
        }

    def enrich_post(self, post_path):
        print(f"🔎 Enriching: {os.path.basename(post_path)}")
        meta = self._parse_post_file(post_path)
        # Require batter and either game_pk or game_str; inning info is optional for matching
        if not meta.get('batter'):
            print("⚠️  Missing batter in post; skipping statcast lookup")
            return None
        if not (meta.get('game_pk') or meta.get('game_str')):
            print("⚠️  Missing game reference (GamePk or Game:) in post; skipping statcast lookup")
            return None

        # Resolve gamePk from post or from teams
        if meta.get('game_pk'):
            game_pk = meta['game_pk']
        else:
            if not meta.get('game_str') or '@' not in meta['game_str']:
                print("⚠️  Missing game info in post; skipping statcast lookup")
                return None
            away_team = meta['game_str'].split('@')[0].strip()
            home_team = meta['game_str'].split('@')[1].strip()
            game_pk = self._find_game_pk(away_team, home_team)
            if not game_pk:
                print("❌ Could not find gamePk for", meta.get('game_str'))
                return None

        # Fetch live feed
        feed = self._http_get_json(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
        plays = feed.get('liveData', {}).get('plays', {}).get('allPlays', [])

        # Find the specific HR play
        target_play = None
        for play in plays:
            result = play.get('result', {})
            if result.get('eventType') != 'home_run':
                continue
            about = play.get('about', {})
            # Try to match inning/half when provided
            if meta.get('inning_half') and about.get('halfInning') != meta['inning_half']:
                continue
            if meta.get('inning_num') and int(about.get('inning', 0)) != int(meta['inning_num']):
                continue
            matchup = play.get('matchup', {})
            b = matchup.get('batter', {})
            batter_name = b.get('fullName')
            batter_id = b.get('id')
            if meta.get('batter_id') and str(meta['batter_id']) == str(batter_id):
                target_play = play
                break
            if self._safe_match_name(batter_name, meta.get('batter') or ''):
                target_play = play
                break
        
        if not target_play and meta.get('batter'):
            # Fallback: pick any HR by batter
            for play in plays:
                if play.get('result', {}).get('eventType') == 'home_run':
                    batter_name = play.get('matchup', {}).get('batter', {}).get('fullName')
                    if self._safe_match_name(batter_name, meta['batter']):
                        target_play = play
                        break

        if not target_play:
            print("❌ Could not locate the HR play for", meta['batter'])
            return None

        statcast = self._extract_statcast_from_play(target_play)
        if not statcast:
            print("⚠️  No statcast data available for this play")
            return None

        # Build output record
        record = {
            'batter': meta['batter'],
            'game': meta['game_str'],
            'inning': f"{meta['inning_half']} {meta['inning_num']}",
            'pitcher': meta['pitcher'],
            'statcast': statcast
        }

        # Save JSON next to posts
        # Determine homer number from filename (supports gamePk-atBatIndex)
        m = re.search(r"tonights_homer_([0-9]+(?:-[0-9]+)?)_", os.path.basename(post_path))
        homer_num = m.group(1) if m else 'unknown'
        out_path = os.path.join(self.output_dir, f"homer_{homer_num}.json")
        with open(out_path, 'w') as f:
            json.dump(record, f, indent=2)
        print(f"✅ Saved: {out_path}")
        return out_path

    def enrich_all(self):
        if not os.path.exists(self.posts_dir):
            print(f"❌ Posts directory not found: {self.posts_dir}")
            return []
        files = [
            os.path.join(self.posts_dir, f)
            for f in os.listdir(self.posts_dir)
            if f.startswith('tonights_homer_') and f.endswith('.txt')
        ]
        files.sort()
        results = []
        for path in files:
            out = self.enrich_post(path)
            if out:
                results.append(out)
        print(f"🎉 Enriched {len(results)} posts with Statcast data")
        return results


def main():
    import sys
    print("📊 STATCAST ENRICHER 📊")
    print("======================")
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    enricher = StatcastEnricher(date_arg)
    enricher.enrich_all()

if __name__ == "__main__":
    main()
