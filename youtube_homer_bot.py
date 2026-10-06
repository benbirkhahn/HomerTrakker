#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
YouTube Home Run Bot - Automatically uploads MLB home run compilations to YouTube
100% FREE to use with generous quotas!
"""

import os
import glob
import re
from datetime import datetime, timedelta, timezone
import json
import sys
import argparse
import wsgiref.simple_server
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
from pathlib import Path
import subprocess

# YouTube API imports
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, _RedirectWSGIApp, _WSGIRequestHandler
import urllib.request, json as jsonlib, os

BASE_DIR = Path(__file__).resolve().parent
EASTERN = ZoneInfo("America/New_York")


def load_local_env(path=BASE_DIR / '.homer.env'):
    try:
        if not path.exists():
            return
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = re.sub(r"\s+#.*$", "", value).strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except Exception as e:
        print(f"⚠️  Could not load local env file {path}: {e}")


load_local_env()

OAUTH_CALLBACK_HOST = os.getenv('HOMER_YT_OAUTH_CALLBACK_HOST', 'localhost')
OAUTH_CALLBACK_BIND_ADDR = os.getenv('HOMER_YT_OAUTH_CALLBACK_BIND_ADDR', '0.0.0.0')
OAUTH_CALLBACK_PORT = int(os.getenv('HOMER_YT_OAUTH_CALLBACK_PORT', '8080'))


class YouTubeHomeRunBot:
    def __init__(self, force_reauth: bool = False):
        """Initialize YouTube bot with API credentials"""
        # Scopes: upload videos and (optionally) update metadata
        # Set HOMER_YT_MINIMAL_SCOPES=1 to restrict to upload-only (no re-consent needed for existing tokens)
        if os.getenv('HOMER_YT_MINIMAL_SCOPES') == '1':
            self.scopes = ['https://www.googleapis.com/auth/youtube.upload']
        else:
            self.scopes = [
                'https://www.googleapis.com/auth/youtube.upload',
                'https://www.googleapis.com/auth/youtube'
            ]
        self.api_service_name = 'youtube'
        self.api_version = 'v3'
        self.credentials_file = str(BASE_DIR / 'config' / 'youtube_credentials.json')
        self.token_file = str(BASE_DIR / 'youtube_token.json')
        # Upload-once ledger under ~/.homer/uploads.json
        self.state_dir = Path.home() / '.homer'
        self.ledger_path = self.state_dir / 'uploads.json'
        self.queue_path = self.state_dir / 'youtube_queue.json'
        self.analytics_summary_path = self.state_dir / 'youtube_analytics_summary.json'
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Default to scheduled publishing so a burst of HRs does not go out all at once.
        # Set HOMER_YT_PUBLISH_MODE=immediate to preserve the old behavior.
        self.publish_mode = os.getenv('HOMER_YT_PUBLISH_MODE', 'scheduled').strip().lower()
        self.publish_start_delay_minutes = int(os.getenv('HOMER_YT_PUBLISH_START_DELAY_MINUTES', '15'))
        self.publish_gap_minutes = int(os.getenv('HOMER_YT_PUBLISH_GAP_MINUTES', '90'))
        self.publish_window_start_hour = int(os.getenv('HOMER_YT_PUBLISH_WINDOW_START_HOUR', '16'))
        self.publish_window_end_hour = int(os.getenv('HOMER_YT_PUBLISH_WINDOW_END_HOUR', '24'))
        self.publish_catchup_queue_threshold = int(os.getenv('HOMER_YT_CATCHUP_QUEUE_THRESHOLD', '16'))
        self.publish_normal_window_start_hour = int(os.getenv('HOMER_YT_NORMAL_WINDOW_START_HOUR', '16'))
        self.publish_normal_window_end_hour = int(os.getenv('HOMER_YT_NORMAL_WINDOW_END_HOUR', '24'))
        self.publish_max_per_day = int(os.getenv('HOMER_YT_MAX_PUBLISHES_PER_DAY', '4'))
        self.publish_max_horizon_days = int(os.getenv('HOMER_YT_MAX_HORIZON_DAYS', '2'))
        self.publish_max_queue_items = int(os.getenv('HOMER_YT_MAX_QUEUE_ITEMS', '8'))
        self.publish_min_score = float(os.getenv('HOMER_YT_MIN_SCORE', '0'))
        self.publish_backlog_min_score = float(os.getenv('HOMER_YT_BACKLOG_MIN_SCORE', '100'))
        self.defer_weak_backlog = os.getenv('HOMER_YT_DEFER_WEAK_BACKLOG', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
        self.suppression_guard_enabled = os.getenv('HOMER_YT_SUPPRESSION_GUARD', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
        self.suppression_slow_gap_minutes = int(os.getenv('HOMER_YT_SUPPRESSION_SLOW_GAP_MINUTES', '90'))
        self.suppression_slow_max_per_day = int(os.getenv('HOMER_YT_SUPPRESSION_SLOW_MAX_PER_DAY', '4'))
        self._analytics_summary = self._load_analytics_summary()
        self._apply_adaptive_publish_policy()
        
        print("🎬 YouTube Home Run Bot initialized!")
        
        # Authenticate with YouTube API
        self.youtube = self.authenticate(force_reauth=force_reauth)
        if not self.youtube:
            print("❌ Failed to authenticate with YouTube API")
            return
        
        print("✅ YouTube API authenticated successfully!")
    
    def authenticate(self, force_reauth: bool = False):
        """Authenticate with YouTube API"""
        credentials = None
        noninteractive = (
            not force_reauth and (
                os.getenv('HOMER_NONINTERACTIVE') == '1' or
                os.getenv('N8N_RUNNER') == '1' or
                (not sys.stdin.isatty() and not sys.stdout.isatty())
            )
        )

        if force_reauth and os.path.exists(self.token_file):
            try:
                os.remove(self.token_file)
                print(f"🧹 Removed cached token at {self.token_file} to force fresh OAuth consent.")
            except Exception as e:
                print(f"⚠️  Could not remove cached token {self.token_file}: {e}")
        
        # Load existing token
        if not force_reauth and os.path.exists(self.token_file):
            credentials = Credentials.from_authorized_user_file(self.token_file, self.scopes)
        
        # If there are no valid credentials, get new ones
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except Exception as e:
                    print(f"⚠️  Token refresh failed ({e}); falling back to re-auth...")
                    credentials = None
            if not credentials or not credentials.valid:
                if not os.path.exists(self.credentials_file):
                    print("❌ YouTube credentials file not found!")
                    print("📋 Setup required:")
                    print("1. Go to https://console.developers.google.com/")
                    print("2. Create a new project or select existing")
                    print("3. Enable YouTube Data API v3")
                    print("4. Create credentials (OAuth 2.0)")
                    print("5. Download and save as 'youtube_credentials.json'")
                    return None
                if noninteractive:
                    print("❌ YouTube token is missing or invalid, and automation cannot open the OAuth browser.")
                    print(f"🔐 Re-auth required: run `python3 {BASE_DIR / 'youtube_homer_bot.py'} --reauth` in a browser-capable shell once.")
                    return None
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes
                )
                credentials = self._run_manual_oauth_local_server(flow)
                if not credentials:
                    return None
            
            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(credentials.to_json())
        
        try:
            return build(self.api_service_name, self.api_version, credentials=credentials)
        except Exception as e:
            print(f"❌ Failed to build YouTube service: {e}")
            return None

    def _run_manual_oauth_local_server(self, flow):
        """Run a container-safe OAuth flow by printing the URL and listening locally for the callback."""
        redirect_uri = f"http://{OAUTH_CALLBACK_HOST}:{OAUTH_CALLBACK_PORT}/"
        flow.redirect_uri = redirect_uri

        auth_url, _ = flow.authorization_url(prompt='select_account')

        print("Please authorize access to upload to your YouTube channel.")
        print(f"OPEN THIS URL IN YOUR MAC BROWSER: {auth_url}")
        print(f"Waiting for OAuth callback on {redirect_uri}")

        wsgi_app = _RedirectWSGIApp(
            "Authentication complete. You can close this tab and return to the terminal."
        )

        try:
            local_server = wsgiref.simple_server.make_server(
                OAUTH_CALLBACK_BIND_ADDR,
                OAUTH_CALLBACK_PORT,
                wsgi_app,
                handler_class=_WSGIRequestHandler,
            )
        except OSError as e:
            print(f"❌ Could not listen for the OAuth callback on {redirect_uri}: {e}")
            print("Ensure the container can bind the callback port and that Docker publishes the same host port.")
            return None

        try:
            authorization_response = None
            while True:
                local_server.handle_request()
                last_request_uri = getattr(wsgi_app, 'last_request_uri', '')
                query = parse_qs(urlparse(last_request_uri).query)
                if query.get('state') and (query.get('code') or query.get('error')):
                    authorization_response = last_request_uri.replace('http', 'https', 1)
                    break
                print("Ignoring unexpected request on the OAuth callback port; still waiting for Google redirect...")
        finally:
            local_server.server_close()
        flow.fetch_token(authorization_response=authorization_response)
        return flow.credentials

    def _is_scheduled_publish_enabled(self):
        return self.publish_mode not in {'immediate', 'public', 'now', 'off', '0', 'false', 'no'}

    def _utc_now(self):
        return datetime.now(timezone.utc)

    def _publish_at_for_index(self, index: int):
        """Return an RFC3339 publishAt timestamp in UTC for the given queue index."""
        if not self._is_scheduled_publish_enabled():
            return None

        delay_minutes = max(15, self.publish_start_delay_minutes + (index * self.publish_gap_minutes))
        publish_dt = self._utc_now() + timedelta(minutes=delay_minutes)
        return publish_dt.replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    def _parse_float(self, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"(-?\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        try:
            return float(match.group(1))
        except Exception:
            return None

    def _load_analytics_summary(self):
        try:
            if self.analytics_summary_path.exists():
                return json.loads(self.analytics_summary_path.read_text())
        except Exception as e:
            print(f"⚠️  Analytics summary unavailable: {e}")
        return {}

    def _apply_adaptive_publish_policy(self):
        if not self.suppression_guard_enabled:
            return
        guard = (self._analytics_summary or {}).get('suppression_guard') or {}
        if not guard.get('triggered'):
            return
        recommended_gap = int(guard.get('recommended_gap_minutes') or self.suppression_slow_gap_minutes)
        recommended_max = int(guard.get('recommended_max_publishes_per_day') or self.suppression_slow_max_per_day)
        old_gap = self.publish_gap_minutes
        old_max = self.publish_max_per_day
        self.publish_gap_minutes = max(self.publish_gap_minutes, recommended_gap)
        if self.publish_max_per_day <= 0:
            self.publish_max_per_day = recommended_max
        else:
            self.publish_max_per_day = min(self.publish_max_per_day, recommended_max)
        print(
            "🛡️  Suppression guard active: "
            f"gap {old_gap}->{self.publish_gap_minutes} min, "
            f"max/day {old_max}->{self.publish_max_per_day}"
        )

    def _star_power_score(self, batter):
        if not batter:
            return 0.0
        stars = {
            'Aaron Judge': 240, 'Shohei Ohtani': 240, 'Juan Soto': 220,
            'Freddie Freeman': 200, 'Mookie Betts': 200, 'Bryce Harper': 190,
            'Yordan Alvarez': 190, 'Ronald Acuña Jr.': 190, 'Pete Alonso': 180,
            'Vladimir Guerrero Jr.': 175, 'Fernando Tatis Jr.': 175, 'Mike Trout': 175,
            'Elly De La Cruz': 170, 'Oneil Cruz': 165, 'Corbin Carroll': 155,
            'Matt Olson': 150, 'Rafael Devers': 150, 'Manny Machado': 145,
            'Kyle Tucker': 170, 'José Ramírez': 170, 'Jose Ramirez': 170,
            'Jazz Chisholm Jr.': 165, 'Pete Crow-Armstrong': 155,
            'Seiya Suzuki': 145, 'Rhys Hoskins': 140, 'Isaac Paredes': 135,
            'Vinnie Pasquantino': 130, 'Wilyer Abreu': 125,
        }
        if batter in stars:
            return float(stars[batter])
        last_name = batter.split()[-1].lower()
        if last_name in {'judge', 'ohtani', 'soto', 'freeman', 'betts', 'harper'}:
            return 180.0
        return 0.0

    def _score_statcast_features(self, distance, launch_speed, launch_angle, batter):
        score = 0.0
        if distance is not None:
            score += distance * 0.7
            if distance >= 430:
                score += 50.0
        if launch_speed is not None:
            score += launch_speed * 15.0
            if launch_speed >= 110:
                score += 250.0
            elif launch_speed >= 107:
                score += 120.0
            elif launch_speed >= 105:
                score += 60.0
        if launch_angle is not None:
            # Current channel data favors hard-hit balls around 20-29 degrees.
            score += max(0.0, 55.0 - abs(launch_angle - 23.0) * 5.0)
            if launch_angle > 34:
                score -= 140.0
        score += self._star_power_score(batter)
        score += self._feature_lift_score(distance, launch_speed, launch_angle)
        return score

    def _feature_bucket(self, feature, value):
        if value is None:
            return None
        if feature == 'exit_velocity':
            if value >= 110:
                return '110+'
            if value >= 107:
                return '107-109.9'
            if value >= 105:
                return '105-106.9'
            if value >= 100:
                return '100-104.9'
            return '<100'
        if feature == 'launch_angle':
            if value < 20:
                return '<20'
            if value <= 24:
                return '20-24'
            if value <= 29:
                return '25-29'
            if value <= 34:
                return '30-34'
            return '35+'
        if feature == 'distance':
            if value >= 420:
                return '420+'
            if value >= 400:
                return '400-419'
            if value >= 380:
                return '380-399'
            return '<380'
        return None

    def _feature_lift_score(self, distance, launch_speed, launch_angle):
        lifts = (self._analytics_summary or {}).get('feature_lifts') or {}
        total = 0.0
        for feature, value in [
            ('exit_velocity', launch_speed),
            ('launch_angle', launch_angle),
            ('distance', distance),
        ]:
            bucket = self._feature_bucket(feature, value)
            meta = ((lifts.get(feature) or {}).get(bucket) or {}) if bucket else {}
            try:
                if int(meta.get('count') or 0) >= 3:
                    total += float(meta.get('rank_score') or 0.0)
            except Exception:
                continue
        return max(-220.0, min(220.0, total))

    def _freshness_score(self, today):
        if not today:
            return 0.0
        try:
            homer_date = datetime.fromisoformat(str(today)).date()
        except Exception:
            return 0.0
        days_old = (self._utc_now().astimezone(EASTERN).date() - homer_date).days
        if days_old <= 0:
            return 320.0
        if days_old == 1:
            return 200.0
        if days_old == 2:
            return 100.0
        if days_old == 3:
            return 0.0
        return -min(450.0, (days_old - 3) * 75.0)

    def _score_video_title(self, title, today=None):
        if not title:
            return 0.0
        parsed = self._parse_title_features(title)
        batter = parsed.get('batter')
        distance = parsed.get('distance')
        launch_speed = parsed.get('launch_speed')
        launch_angle = parsed.get('launch_angle')
        score = self._score_statcast_features(distance, launch_speed, launch_angle, batter)
        score += self._freshness_score(today)
        try:
            player_meta = ((self._analytics_summary or {}).get('by_player') or {}).get(batter)
            if player_meta:
                uploads = float(player_meta.get('uploads') or 0)
                reliability = min(1.0, uploads / 3.0)
                score += float(player_meta.get('popularity_rank_score') or 0.0) * (2.0 + reliability * 3.0)
        except Exception:
            pass
        return round(score, 3)

    def _parse_title_features(self, title):
        player_match = re.match(r"^(.*?)\s+(?:HR|Home Run)\b", title or "", re.I)
        batter = player_match.group(1).strip() if player_match else None
        if batter:
            batter = re.sub(r"\s+\d+(?:\.\d+)?\s*(?:MPH|FT)\s*$", "", batter, flags=re.I).strip()

        def title_stat(patterns):
            for pattern in patterns:
                match = re.search(pattern, title or "", re.I)
                if match:
                    return self._parse_float(match.group(1))
            return None

        return {
            'batter': batter,
            'distance': title_stat([r"Distance\s+(\d+)", r"(\d+)\s*ft"]),
            'launch_speed': title_stat([r"Exit Velocity\s+([\d.]+)", r"([\d.]+)\s*MPH"]),
            'launch_angle': title_stat([r"Launch Angle\s+([\d.]+)", r"([\d.]+)\s*(?:deg|°)"]),
        }

    def _optimized_title_from_title(self, title):
        parsed = self._parse_title_features(title)
        batter = parsed.get('batter')
        if not batter:
            return title
        distance = parsed.get('distance')
        launch_speed = parsed.get('launch_speed')
        launch_angle = parsed.get('launch_angle')
        star_score = self._star_power_score(batter)

        if launch_speed is not None and launch_speed >= 110:
            hook = f"{launch_speed:.1f} MPH HR"
        elif distance is not None and distance >= 420:
            hook = f"{int(round(distance))} FT HR"
        elif star_score >= 145:
            hook = "Home Run"
        elif launch_speed is not None and launch_speed >= 105:
            hook = f"{launch_speed:.1f} MPH HR"
        elif distance is not None and distance >= 400:
            hook = f"{int(round(distance))} FT HR"
        elif distance is None and launch_speed is None:
            hook = "Home Run"
        else:
            return title

        title = f"{batter} {hook} #Shorts"
        return title[:100]

    def _optimized_tags_from_snippet(self, snippet, title):
        tags = list(snippet.get('tags') or [])
        parsed = self._parse_title_features(title)
        additions = ['MLB', 'baseball', 'home run', 'Shorts', 'MLBShorts']
        if parsed.get('batter'):
            additions.append(parsed['batter'])
        if parsed.get('distance') is not None:
            additions.append(f"{int(round(parsed['distance']))}FT")
        if parsed.get('launch_speed') is not None:
            additions.append(f"{int(round(parsed['launch_speed']))}MPH")
        for tag in additions:
            if tag and tag not in tags:
                tags.append(tag)
        return tags[:25]

    def _score_homer(self, homer_num, today=None):
        """Simple ranking score used to prioritize stronger clips when the queue backs up."""
        info = self.extract_homer_info(homer_num, today)
        distance = self._parse_float(info.get('distance'))
        launch_speed = self._parse_float(info.get('launch_speed'))
        launch_angle = self._parse_float(info.get('launch_angle'))
        batter = info.get('batter') or 'MLB Player'

        score = self._score_statcast_features(distance, launch_speed, launch_angle, batter)
        score += self._freshness_score(today)

        try:
            player_meta = ((self._analytics_summary or {}).get('by_player') or {}).get(batter)
            if player_meta:
                uploads = float(player_meta.get('uploads') or 0)
                reliability = min(1.0, uploads / 3.0)
                score += float(player_meta.get('popularity_rank_score') or 0.0) * (2.0 + reliability * 3.0)
        except Exception as e:
            print(f"⚠️  Analytics summary unavailable: {e}")

        return round(score, 3)

    def _load_queue(self):
        try:
            if self.queue_path.exists():
                with open(self.queue_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault('items', {})
                        data.setdefault('meta', {})
                        return data
        except Exception as e:
            print(f"⚠️  Could not load queue: {e}")
        return {'meta': {}, 'items': {}}

    def _save_queue(self, queue):
        try:
            queue.setdefault('meta', {})
            queue['meta']['updated_at'] = self._utc_now().isoformat()
            with open(self.queue_path, 'w') as f:
                json.dump(queue, f, indent=2)
        except Exception as e:
            print(f"⚠️  Could not save queue: {e}")

    def _prune_queue(self, max_age_days=3):
        """Remove uploaded items older than max_age_days from the queue to prevent unbounded growth."""
        queue = self._load_queue()
        now = self._utc_now()
        to_remove = []
        for key, item in (queue.get('items') or {}).items():
            if item.get('status') != 'uploaded':
                continue
            uploaded_at = item.get('uploaded_at')
            if not uploaded_at:
                continue
            try:
                dt = datetime.fromisoformat(uploaded_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = (now - dt).total_seconds() / 86400
                if age_days > max_age_days:
                    to_remove.append(key)
            except Exception:
                continue
        for key in to_remove:
            del queue['items'][key]
        if to_remove:
            self._save_queue(queue)
            print(f"🧹 Pruned {len(to_remove)} old uploaded items from queue")
        return len(to_remove)

    def _queue_key(self, today, homer_num):
        return f"{today}:{homer_num}"

    def _queue_items_sorted(self, queue):
        items = list((queue or {}).get('items', {}).values())
        def sort_key(item):
            publish_at = item.get('publish_at') or ''
            priority = -(item.get('priority_score') or 0)
            created = item.get('queued_at') or ''
            return (publish_at, priority, created, item.get('key') or '')
        return sorted(items, key=sort_key)

    def _day_slot_count(self, queue, day_str):
        count = 0
        for item in (queue or {}).get('items', {}).values():
            publish_at = item.get('publish_at')
            if not publish_at:
                continue
            try:
                day = datetime.fromisoformat(publish_at.replace('Z', '+00:00')).astimezone(EASTERN).date().isoformat()
                if day == day_str:
                    count += 1
            except Exception:
                continue
        return count

    def _queue_item_count(self, queue):
        return len((queue or {}).get('items', {}))

    def _active_queue_item_count(self, queue):
        active_states = {'reserved', 'queued', 'pending'}
        count = 0
        for item in (queue or {}).get('items', {}).values():
            if (item.get('status') or 'reserved') in active_states:
                count += 1
        return count

    def _future_scheduled_queue_count(self, queue=None):
        queue = queue or self._load_queue()
        now = self._utc_now()
        count = 0
        for item in (queue or {}).get('items', {}).values():
            publish_at = item.get('publish_at')
            if not publish_at:
                continue
            if (item.get('status') or '').lower() in {'failed', 'skipped', 'not_private_scheduled'}:
                continue
            try:
                publish_dt = datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
            except Exception:
                continue
            if publish_dt > now:
                count += 1
        return count

    def _last_publish_at(self, queue):
        latest = None
        for item in (queue or {}).get('items', {}).values():
            # Skip already-uploaded items; they shouldn't block new scheduling
            if item.get('status') == 'uploaded':
                continue
            publish_at = item.get('publish_at')
            if not publish_at:
                continue
            try:
                dt = datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
            except Exception:
                continue
            if latest is None or dt > latest:
                latest = dt
        return latest

    def _publish_window_for_queue(self):
        if self.publish_catchup_queue_threshold <= 0:
            return self.publish_window_start_hour, self.publish_window_end_hour
        try:
            active_count = self._future_scheduled_queue_count()
        except Exception:
            active_count = self.publish_catchup_queue_threshold
        if active_count >= self.publish_catchup_queue_threshold:
            return self.publish_window_start_hour, self.publish_window_end_hour
        return self.publish_normal_window_start_hour, self.publish_normal_window_end_hour

    def _effective_publish_min_score(self, queue):
        min_score = self.publish_min_score
        if self.publish_catchup_queue_threshold > 0:
            try:
                if self._future_scheduled_queue_count(queue) >= self.publish_catchup_queue_threshold:
                    min_score = max(min_score, self.publish_backlog_min_score)
            except Exception:
                pass
        return min_score

    def _next_publish_slot(self, queue, anchor_utc=None, window_start_hour=None, window_end_hour=None):
        """Pick the next future publish slot in Eastern time."""
        if not self._is_scheduled_publish_enabled():
            return None

        anchor_utc = anchor_utc or self._utc_now()
        start_utc = anchor_utc + timedelta(minutes=self.publish_start_delay_minutes)
        last_reserved = self._last_publish_at(queue)
        if last_reserved is not None:
            start_utc = max(start_utc, last_reserved + timedelta(minutes=self.publish_gap_minutes))

        cursor = start_utc.astimezone(EASTERN)
        if window_start_hour is None or window_end_hour is None:
            window_start_hour, window_end_hour = self._publish_window_for_queue()
        for _ in range(30):  # enough to cover long backlogs without going unbounded
            day_start = cursor.replace(
                hour=window_start_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if window_end_hour >= 24:
                day_end = cursor.replace(hour=23, minute=59, second=59, microsecond=0)
            else:
                day_end = cursor.replace(
                    hour=window_end_hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            if cursor < day_start:
                cursor = day_start
            if cursor > day_end:
                cursor = (day_start + timedelta(days=1)).replace(
                    hour=window_start_hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                continue

            day_key = cursor.date().isoformat()
            if self.publish_max_per_day > 0 and self._day_slot_count(queue, day_key) >= self.publish_max_per_day:
                cursor = (day_start + timedelta(days=1)).replace(
                    hour=window_start_hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                continue

            candidate = cursor.astimezone(timezone.utc).replace(microsecond=0)
            return candidate.isoformat().replace('+00:00', 'Z')

        return cursor.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    def _slot_distance_days(self, publish_at):
        try:
            dt = datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
            return (dt.astimezone(EASTERN).date() - self._utc_now().astimezone(EASTERN).date()).days
        except Exception:
            return 999

    def _discover_compiled_homers(self, today):
        patterns = [
            str(BASE_DIR / f"Shorts_Ready/Homer_*_{today}_SHORT.mp4"),
            str(BASE_DIR / f"YouTube_Shorts_Ready/Homer_*_{today}.mp4"),
            str(BASE_DIR / f"YouTube_Shorts_Ready/Homer_*_{today}_SHORT.mp4"),
        ]
        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))
        unique = {}
        for path in files:
            match = re.search(r'Homer_([A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)_', os.path.basename(path))
            if not match:
                continue
            homer_num = match.group(1)
            unique[homer_num] = path
        return unique

    def _env_flag(self, name, default=False):
        raw = os.getenv(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}

    def _find_post_files(self, homer_num, today):
        posts_dir = str(BASE_DIR / 'MLB_HomeRun_Posts' / today)
        post_files = glob.glob(f"{posts_dir}/tonights_homer_{homer_num}_*.txt")
        if not post_files:
            post_files = sorted(glob.glob(f"{posts_dir}/_archived_*/tonights_homer_{homer_num}_*.txt"))

        if not post_files and re.fullmatch(r"\d+", str(homer_num)):
            all_posts = sorted(glob.glob(f"{posts_dir}/tonights_homer_*_*.txt"))
            try:
                idx = int(homer_num)
                if 1 <= idx <= len(all_posts):
                    post_files = [all_posts[idx - 1]]
            except Exception:
                pass

        return sorted(post_files)

    def _read_source_post(self, homer_num, today):
        post_files = self._find_post_files(homer_num, today)
        if not post_files:
            return None, ""
        try:
            with open(post_files[0], 'r') as f:
                return post_files[0], f.read()
        except Exception as e:
            print(f"⚠️  Could not read source post for homer #{homer_num}: {e}")
            return post_files[0], ""

    def _caption_from_post(self, content):
        lines = content.splitlines()
        caption_lines = []
        in_caption = False
        for line in lines:
            if line.startswith('CAPTION:'):
                in_caption = True
                continue
            if line.startswith('HASHTAGS:'):
                break
            if in_caption and line.strip():
                caption_lines.append(line.strip())
        return "\n".join(caption_lines).strip()

    def _video_counts_from_post(self, content):
        urls = re.findall(r'https?://[^\s\n]+\.mp4(?:\?[^\s\n]+)?', content or '', flags=re.I)
        return {
            'broadcast': sum(1 for url in urls if 'mlb-cuts-diamond.mlb.com' in url),
            'animated': sum(1 for url in urls if 'darkroom-clips.mlb.com' in url),
            'produced': sum(1 for url in urls if 'bdata-producedclips.mlb.com' in url),
            'total': len(urls),
        }

    def _source_post_status(self, homer_num, today, require_both=None):
        if require_both is None:
            require_both = self._env_flag('HOMER_REQUIRE_BOTH', default=True)
        post_path, content = self._read_source_post(homer_num, today)
        if not post_path:
            return False, 'source_post_missing'
        caption = self._caption_from_post(content)
        if not caption:
            return False, 'caption_missing'
        if not re.search(r"^Batter:\s*(?!\s*$).+", content, flags=re.MULTILINE):
            return False, 'batter_missing'
        counts = self._video_counts_from_post(content)
        if require_both and not (counts['broadcast'] and counts['animated']):
            return False, f"missing_required_clip(broadcast={counts['broadcast']}, animated={counts['animated']})"
        return True, 'ready'

    def _sync_queue_for_today(self, today):
        queue = self._load_queue()
        discovered = self._discover_compiled_homers(today)
        led = self._load_ledger()

        new_entries = []
        for homer_num, video_path in discovered.items():
            key = self._queue_key(today, homer_num)
            if key in queue['items']:
                continue
            if led.get(key):
                continue
            ready, reason = self._source_post_status(homer_num, today)
            if not ready:
                print(f"🛑 Queue planner: skipping {homer_num}; source post not upload-ready ({reason})")
                continue
            new_entries.append((homer_num, video_path))

        if not new_entries:
            return queue

        scored = []
        min_score = self._effective_publish_min_score(queue)
        for homer_num, video_path in new_entries:
            score = self._score_homer(homer_num, today)
            if score < min_score:
                print(f"🧠 Queue planner: skipping {homer_num}; score {score} < min {min_score}")
                continue
            scored.append((homer_num, video_path, score))

        if not scored:
            return queue

        scored.sort(key=lambda pair: (-pair[2], self._parse_float(pair[0]) or 0.0))
        available_slots = max(0, self.publish_max_queue_items - self._active_queue_item_count(queue))
        if available_slots <= 0:
            print("🧠 Queue planner: queue is full; deferring new items")
            return queue

        selected = scored[:available_slots]
        dropped = scored[available_slots:]
        if dropped:
            print(
                f"🧠 Queue planner: reserving {len(selected)} clip(s), "
                f"skipping {len(dropped)} lower-priority clip(s)"
            )
        else:
            print(f"🧠 Queue planner: reserving {len(selected)} new video(s)")

        for homer_num, video_path, score in selected:
            key = self._queue_key(today, homer_num)
            publish_at = self._next_publish_slot(queue)
            if publish_at and self._slot_distance_days(publish_at) >= self.publish_max_horizon_days:
                print(f"🧠 Queue planner: stopping before {homer_num}; publish horizon exceeded")
                break
            queue['items'][key] = {
                'key': key,
                'today': today,
                'homer_num': homer_num,
                'video_path': video_path,
                'publish_at': publish_at,
                'priority_score': score,
                'queued_at': self._utc_now().isoformat(),
                'status': 'reserved',
                'video_id': None,
            }
        self._save_queue(queue)
        return queue
    
    def extract_homer_info(self, homer_num, today=None):
        """Extract batter and enriched stats for metadata"""
        if today is None:
            today = datetime.now().strftime('%Y-%m-%d')
        
        posts_dir = str(BASE_DIR / 'MLB_HomeRun_Posts' / today)
        post_files = self._find_post_files(homer_num, today)
        
        default_info = {
            'batter': 'MLB Player',
            'team': 'MLB',
            'distance': '',
            'launch_speed': '',
            'launch_angle': '',
            'description': '',
            'caption': ''
        }
        
        info = default_info.copy()
        
        # Try to load enriched statcast json
        # Prefer per-atBat json; fallback to gamePk-only json if homer_num includes "-"
        stats_json = os.path.join(posts_dir, 'stats', f'homer_{homer_num}.json')
        if not os.path.exists(stats_json) and '-' in str(homer_num):
            gp = str(homer_num).split('-')[0]
            stats_json = os.path.join(posts_dir, 'stats', f'homer_{gp}.json')
        if not os.path.exists(stats_json):
            # Fallback: look in archived folder(s)
            arch_candidates = sorted(glob.glob(os.path.join(posts_dir, f"_archived_*/stats/homer_{homer_num}.json")))
            if not arch_candidates and '-' in str(homer_num):
                arch_candidates = sorted(glob.glob(os.path.join(posts_dir, f"_archived_*/stats/homer_{str(homer_num).split('-')[0]}.json")))
            if arch_candidates:
                stats_json = arch_candidates[-1]
        if os.path.exists(stats_json):
            try:
                with open(stats_json, 'r') as f:
                    stats = json.load(f)
                info['batter'] = stats.get('batter', info['batter'])
                info['game'] = stats.get('game', '')
                info['inning'] = stats.get('inning', '')
                info['pitcher'] = stats.get('pitcher', '')
                sc = stats.get('statcast', {})
                if sc.get('totalDistance'):
                    info['distance'] = f"{int(round(float(sc['totalDistance'])))} feet"
                if sc.get('launchSpeed'):
                    info['launch_speed'] = f"{round(float(sc['launchSpeed']),1)} mph"
                if sc.get('launchAngle'):
                    info['launch_angle'] = f"{round(float(sc['launchAngle']),1)}°"
            except Exception as e:
                print(f"⚠️  Could not parse stats json: {e}")
        
        if post_files:
            try:
                with open(post_files[0], 'r') as f:
                    content = f.read()
                lines = content.split('\n')
                # Extract batter if not filled
                if info['batter'] == 'MLB Player':
                    m = re.search(r"Batter:\s*(.+)", content)
                    if m:
                        info['batter'] = m.group(1).strip()
                # Fallback: parse caption line style "🔥 Name"
                if info['batter'] == 'MLB Player':
                    m = re.search(r"^\s*🔥\s*([^\n]+)$", content, flags=re.MULTILINE)
                    if m:
                        info['batter'] = m.group(1).strip()
                # Try to hydrate stat fields using the full homer ID from the post filename
                try:
                    m = re.search(r"tonights_homer_([A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)_", os.path.basename(post_files[0]))
                    if m:
                        full_id = m.group(1)
                        alt_stats = os.path.join(posts_dir, 'stats', f'homer_{full_id}.json')
                        if os.path.exists(alt_stats):
                            with open(alt_stats, 'r') as sf:
                                stats = json.load(sf)
                            info['batter'] = stats.get('batter', info.get('batter'))
                            info['game'] = stats.get('game', info.get('game',''))
                            info['inning'] = stats.get('inning', info.get('inning',''))
                            info['pitcher'] = stats.get('pitcher', info.get('pitcher',''))
                            sc = stats.get('statcast', {}) or {}
                            if sc.get('totalDistance'):
                                info['distance'] = f"{int(round(float(sc['totalDistance'])))} feet"
                            if sc.get('launchSpeed'):
                                info['launch_speed'] = f"{round(float(sc['launchSpeed']),1)} mph"
                            if sc.get('launchAngle'):
                                info['launch_angle'] = f"{round(float(sc['launchAngle']),1)}°"
                except Exception as e:
                    print(f"⚠️  Could not hydrate from full-id stats: {e}")
                # Use caption as description
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
                if caption_lines:
                    info['caption'] = '\n'.join(caption_lines)
                    info['description'] = ' '.join(caption_lines)
            except Exception as e:
                print(f"⚠️  Could not read post file: {e}")
        
        return info
    
    def create_video_metadata(self, homer_num, video_path, today=None, privacy=None, publish_at=None):
        """Create metadata for YouTube upload with Statcast-rich details"""
        import math
        info = self.extract_homer_info(homer_num, today)
        
        # Normalized stat fields
        dist_raw = info.get('distance') or ''          # e.g., '411 feet'
        ev_raw = info.get('launch_speed') or ''        # e.g., '100.9 mph'
        la_raw = info.get('launch_angle') or ''        # e.g., '28.0°'
        
        # Numeric versions for tags/formatting
        def to_int(s):
            try:
                return int(round(float(''.join(ch for ch in s if (ch.isdigit() or ch=='.')))))
            except:
                return None
        def to_float(s):
            try:
                return float(''.join(ch for ch in s if (ch.isdigit() or ch=='.')))
            except:
                return None
        dist_int = to_int(dist_raw) if dist_raw else None
        ev_float = to_float(ev_raw) if ev_raw else None
        la_float = to_float(la_raw) if la_raw else None
        
        dist_str = f"{dist_int} FT" if dist_int is not None else ''
        ev_str = f"{ev_float:.1f} MPH" if ev_float is not None else ''
        la_str = f"{la_float:.1f}°" if la_float is not None else (la_raw or '')
        
        # Build title in the explicit style user requested
        #   "{Player} HR — Distance 411 FT | Launch Angle 28° | Exit Velocity 100.9 MPH #Shorts"
        parts = []
        if dist_str:
            parts.append(f"Distance {dist_str}")
        if la_str:
            parts.append(f"Launch Angle {la_str}")
        if ev_str:
            parts.append(f"Exit Velocity {ev_str}")
        spec_line = " | ".join(parts)
        
        base = f"{info['batter']} HR"
        title = base + (f" — {spec_line}" if spec_line else "")
        
        # Try to get duration and shorts flag
        duration_str = ""
        try:
            import subprocess
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path
            ], capture_output=True, text=True)
            if result.returncode == 0:
                info_data = json.loads(result.stdout)
                duration = float(info_data['format']['duration'])
                if duration <= 60:
                    duration_str = " #Shorts"
        except:
            pass
        
        # Assemble concise two-line description + hashtag line
        line1_parts = []
        if dist_int is not None:
            line1_parts.append(f"{dist_int} FT")
        if la_float is not None:
            line1_parts.append(f"{la_float:.0f}° LA")
        if ev_float is not None:
            line1_parts.append(f"{ev_float:.1f} MPH EV")
        line1 = "Statcast: " + " • ".join(line1_parts) if line1_parts else ""
        
        line2_parts = []
        if info.get('game'):
            line2_parts.append(f"{info['game']}")
        if info.get('inning'):
            line2_parts.append(f"— {info['inning']}")
        if info.get('pitcher'):
            line2_parts.append(f"• vs {info['pitcher']}")
        line2 = "Matchup: " + " ".join(line2_parts) if line2_parts else ""
        
        # Hashtags (6–9)
        def tagify(s):
            return '#' + re.sub(r'[^A-Za-z0-9]', '', s) if s else None
        player_tag = tagify(info.get('batter'))
        away_tag = home_tag = None
        if info.get('game') and '@' in info['game']:
            away = info['game'].split('@')[0].strip()
            home = info['game'].split('@')[1].strip()
            away_tag = tagify(away)
            home_tag = tagify(home)
        dist_tag = f"#{dist_int}FT" if dist_int is not None else None
        ev_tag = f"#{int(round(ev_float))}MPH" if ev_float is not None else None
        la_tag = f"#{int(round(la_float))}Degrees" if la_float is not None else None
        style_tag = '#Moonshot' if (la_float is not None and la_float >= 35) else ('#Laser' if (la_float is not None and la_float <= 20) else None)
        hashtags = [t for t in ['#MLB','#HomeRun','#MLBShorts','#Statcast',player_tag,away_tag,home_tag,dist_tag,ev_tag,style_tag] if t]
        hashtags_line = ' '.join(hashtags[:9])
        
        # Final description: preserve the source post caption, then append compact Statcast context.
        caption = (info.get('caption') or info.get('description') or '').strip()
        description = "\n\n".join([x for x in [caption, line1, line2] if x])
        if hashtags_line:
            description += ("\n" if description else "") + hashtags_line
        description = description[:4900]
        
        # Tags for API (not visible) – keep simple
        tags = ['MLB','baseball','home run','MLBShorts','Statcast']
        if info.get('batter'):
            tags.append(info['batter'])
        if away_tag:
            tags.append(away_tag[1:])
        if home_tag:
            tags.append(home_tag[1:])
        if dist_tag:
            tags.append(dist_tag[1:])
        if ev_tag:
            tags.append(ev_tag[1:])
        
        return {
            'title': (title + duration_str)[:100],
            'description': description,
            'tags': tags,
            'category': '17',
            'privacy': privacy or ('private' if publish_at else ('private' if self._is_scheduled_publish_enabled() else 'public')),
            'publish_at': publish_at,
            # include stat fields for thumbnail overlay convenience
            'distance': info.get('distance'),
            'launch_speed': info.get('launch_speed'),
            'launch_angle': info.get('launch_angle'),
            'batter': info.get('batter'),
            'game': info.get('game'),
            'inning': info.get('inning'),
            'pitcher': info.get('pitcher')
        }
    
    def _find_font(self):
        candidates = [
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/System/Library/Fonts/Helvetica.ttc'
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _generate_thumbnail(self, video_path, info):
        """Generate a thumbnail JPG from the video with optional overlayed stats"""
        thumb_dir = str(BASE_DIR / 'Thumbnails_Ready')
        os.makedirs(thumb_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(video_path))[0]
        thumb_path = os.path.join(thumb_dir, base + '.jpg')
        font = self._find_font()
        try:
            import subprocess
            if font:
                # Build overlay text
                dist_raw = info.get('distance') or ''
                ev_raw = info.get('launch_speed') or ''
                la_raw = info.get('launch_angle') or ''
                dist_str = dist_raw.replace(' feet', ' FT') if dist_raw else ''
                ev_str = ev_raw.replace(' mph', ' MPH') if ev_raw else ''
                # Escape characters that break ffmpeg drawtext quoting
                def _esc(s: str) -> str:
                    return s.replace(':','\\:').replace("'","\\\\'")
                top_text = _esc(f"{info.get('batter','HR')} HR")
                bottom_parts = [x for x in [dist_str, ev_str, la_raw] if x]
                bottom_text = _esc("  |  ".join(bottom_parts))
                vf = (
                    f"scale=1280:-1,drawbox=x=0:y=0:w=iw:h=120:color=black@0.55:t=fill,"
                    f"drawtext=fontfile={font}:text='{top_text}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y=20,"
                    f"drawbox=x=0:y=h-120:w=iw:h=120:color=black@0.55:t=fill,"
                    f"drawtext=fontfile={font}:text='{bottom_text}':fontcolor=white:fontsize=42:x=(w-text_w)/2:y=h-100"
                )
                subprocess.run(['ffmpeg','-y','-ss','00:00:01','-i',video_path,'-vframes','1','-vf',vf,thumb_path],
                               check=True,capture_output=True)
            else:
                subprocess.run(['ffmpeg','-y','-ss','00:00:01','-i',video_path,'-vframes','1','-vf','scale=1280:-1',thumb_path],
                               check=True,capture_output=True)
            return thumb_path
        except Exception as e:
            print(f"⚠️  Thumbnail generation failed: {e}")
            return None

    def _set_thumbnail(self, video_id, thumb_path):
        try:
            if not thumb_path or not os.path.exists(thumb_path):
                return
            media = MediaFileUpload(thumb_path, mimetype='image/jpeg')
            self.youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
            print("🖼️  Custom thumbnail set")
        except Exception as e:
            print(f"⚠️  Thumbnail upload failed: {e}")

    def upload_video(self, video_path, metadata):
        """Upload a video to YouTube"""
        try:
            print(f"📤 Uploading: {os.path.basename(video_path)}")
            print(f"🏷️  Title: {metadata['title']}")
            
            # Create the upload request body
            body = {
                'snippet': {
                    'title': metadata['title'],
                    'description': metadata['description'],
                    'tags': metadata['tags'],
                    'categoryId': metadata['category']
                },
                'status': {
                    'privacyStatus': metadata['privacy'],
                    'selfDeclaredMadeForKids': False
                }
            }

            publish_at = metadata.get('publish_at')
            if publish_at:
                if body['status']['privacyStatus'] != 'private':
                    body['status']['privacyStatus'] = 'private'
                body['status']['publishAt'] = publish_at
            
            # Create media upload object
            media = MediaFileUpload(
                video_path,
                chunksize=1024*1024,  # 1MB chunks
                resumable=True
            )
            
            # Execute the upload
            insert_request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Perform the upload
            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"  📊 Upload progress: {progress}%")
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Try to set a nice thumbnail
            thumb = self._generate_thumbnail(video_path, metadata)
            self._set_thumbnail(video_id, thumb)

            # Post-upload cleanup to save disk space
            try:
                if thumb and os.path.exists(thumb):
                    os.remove(thumb)
            except Exception as e:
                print(f"⚠️  Could not delete thumbnail: {e}")
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                    print("🧹 Deleted local video after upload")
            except Exception as e:
                print(f"⚠️  Could not delete uploaded video: {e}")
            
            # Log posted video locally
            try:
                from datetime import datetime
                log_dir = BASE_DIR / 'logs'
                log_dir.mkdir(exist_ok=True)
                line = f"{datetime.now().isoformat()} | {video_id} | {metadata['title']} | {video_url}\n"
                with open(log_dir / 'posted.log', 'a') as lf:
                    lf.write(line)
            except Exception as e:
                print(f"⚠️  Could not write posted log: {e}")

            # Optional webhook notifier (Slack/Discord)
            try:
                webhook = os.getenv('HOMER_WEBHOOK_URL')
                if webhook:
                    msg = {
                        'text': f"HomerTrakker posted: {metadata['title']}\n{video_url}",
                        'content': f"HomerTrakker posted: {metadata['title']}\n{video_url}"
                    }
                    req = urllib.request.Request(webhook, data=jsonlib.dumps(msg).encode('utf-8'), headers={'Content-Type':'application/json'})
                    urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:
                print(f"⚠️  Webhook notify failed: {e}")

            print(f"✅ Upload successful!")
            print(f"🔗 Video URL: {video_url}")

            # iMessage notification (optional)
            try:
                self.notify_imessage(f"HomerTrakker posted: {metadata['title']}\n{video_url}")
            except Exception as e:
                print(f"⚠️  iMessage notify failed: {e}")

            return {
                'success': True,
                'video_id': video_id,
                'url': video_url
            }
            
        except HttpError as e:
            print(f"❌ HTTP error during upload: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _load_ledger(self):
        try:
            if self.ledger_path.exists():
                with open(self.ledger_path, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_ledger(self, led):
        try:
            with open(self.ledger_path, 'w') as f:
                json.dump(led, f, indent=2)
        except Exception as e:
            print(f"⚠️  Could not save ledger: {e}")

    def _normalize_phone(self, s):
        if not s:
            return None
        s = str(s).strip()
        if s.startswith('+'):
            return s
        digits = ''.join(ch for ch in s if ch.isdigit())
        if len(digits) == 10:
            return '+1' + digits
        if len(digits) == 11 and digits.startswith('1'):
            return '+' + digits
        return s

    def notify_imessage(self, message: str, phone: str = None):
        """Send an iMessage notification via AppleScript if HOMER_NOTIFY_PHONE is set."""
        try:
            phone = phone or os.getenv('HOMER_NOTIFY_PHONE') or os.getenv('HOMER_NOTIFY_IMESSAGE')
            if not phone:
                return False
            target = self._normalize_phone(phone)
            script = (
                "on run argv\n"
                "  set target to item 1 of argv\n"
                "  set textMsg to item 2 of argv\n"
                "  tell application \"Messages\"\n"
                "    set targetService to first service whose service type is iMessage\n"
                "    set targetBuddy to buddy target of targetService\n"
                "    send textMsg to targetBuddy\n"
                "  end tell\n"
                "end run\n"
            )
            subprocess.run(['osascript', '-', target, message], input=script, text=True, capture_output=True, check=True)
            print(f"📱 iMessage notification sent to {target}")
            return True
        except Exception as e:
            print(f"⚠️  iMessage notify failed: {e}")
            return False

    def _fetch_video_statuses(self, video_ids):
        statuses = {}
        for i in range(0, len(video_ids), 50):
            batch = [v for v in video_ids[i:i + 50] if v]
            if not batch:
                continue
            resp = self.youtube.videos().list(
                part='snippet,status',
                id=','.join(batch),
            ).execute()
            for item in resp.get('items', []):
                statuses[item.get('id')] = item
        return statuses

    def _new_slot_queue(self):
        return {'meta': {}, 'items': {}}

    def _status_update_body(self, video_id, current_status, publish_at):
        status = {
            'privacyStatus': 'private',
            'publishAt': publish_at,
            'selfDeclaredMadeForKids': current_status.get('selfDeclaredMadeForKids', False),
        }
        for key in ['license', 'embeddable', 'publicStatsViewable', 'containsSyntheticMedia']:
            if key in current_status:
                status[key] = current_status[key]
        return {'id': video_id, 'status': status}

    def _recent_reschedule_age_minutes(self, item):
        try:
            value = item.get('rescheduled_at')
            if not value:
                return None
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return (self._utc_now() - dt).total_seconds() / 60.0
        except Exception:
            return None

    def optimize_scheduled_metadata(self, dry_run=True, min_lead_minutes=None):
        """Shorten future private scheduled titles so the strongest hook appears first."""
        queue = self._load_queue()
        now = self._utc_now()
        min_lead_minutes = int(
            min_lead_minutes
            if min_lead_minutes is not None
            else os.getenv('HOMER_YT_RESCHEDULE_MIN_LEAD_MINUTES', '10')
        )
        min_update_at = now + timedelta(minutes=min_lead_minutes)
        candidates = []
        for item in self._queue_items_sorted(queue):
            video_id = item.get('video_id')
            publish_at = item.get('publish_at')
            if not video_id or not publish_at:
                continue
            try:
                publish_dt = datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
            except Exception:
                continue
            if publish_dt <= min_update_at:
                continue
            candidates.append(item)

        if not candidates:
            print("No future queued videos found for metadata optimization.")
            return []

        videos = self._fetch_video_statuses([item['video_id'] for item in candidates])
        updates = []
        for item in candidates:
            video = videos.get(item['video_id'])
            if not video:
                continue
            status = video.get('status') or {}
            if status.get('privacyStatus') != 'private':
                continue
            snippet = video.get('snippet') or {}
            old_title = snippet.get('title') or ''
            new_title = self._optimized_title_from_title(old_title)
            if not new_title or new_title == old_title:
                continue
            updates.append({
                'video_id': item['video_id'],
                'key': item.get('key'),
                'old_title': old_title,
                'new_title': new_title,
                'snippet': snippet,
            })

        for update in updates:
            print(
                f"{update['key']} {update['video_id']}: "
                f"{update['old_title']} -> {update['new_title']} "
                f"{'(dry-run)' if dry_run else ''}"
            )
            if dry_run:
                continue
            snippet = update['snippet']
            body = {
                'id': update['video_id'],
                'snippet': {
                    'title': update['new_title'],
                    'description': snippet.get('description', ''),
                    'tags': self._optimized_tags_from_snippet(snippet, update['old_title']),
                    'categoryId': snippet.get('categoryId', '17'),
                },
            }
            try:
                self.youtube.videos().update(part='snippet', body=body).execute()
            except Exception as e:
                print(f"❌ Metadata optimization failed for {update['video_id']}: {e}")
                update['success'] = False
                update['error'] = str(e)
                continue
            update['success'] = True

        return updates

    def reschedule_pending_posts(self, dry_run=True, reorder=False, min_lead_minutes=None):
        """Reschedule still-private videos using the current queue policy.

        When reorder=True, future private videos are sorted by the latest ranking
        score so stronger clips get earlier slots.
        """
        queue = self._load_queue()
        now = self._utc_now()
        min_lead_minutes = int(
            min_lead_minutes
            if min_lead_minutes is not None
            else os.getenv('HOMER_YT_RESCHEDULE_MIN_LEAD_MINUTES', '10')
        )
        min_reschedule_at = now + timedelta(minutes=min_lead_minutes)
        candidates = []
        protected_slots = []
        for item in self._queue_items_sorted(queue):
            video_id = item.get('video_id')
            publish_at = item.get('publish_at')
            if not video_id or not publish_at:
                continue
            try:
                publish_dt = datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
            except Exception:
                continue
            if publish_dt <= min_reschedule_at:
                item['reschedule_status'] = 'too_close_to_publish'
                protected_slots.append(item)
                continue
            candidates.append(item)

        if not candidates:
            print("No future queued videos found.")
            return []

        statuses = self._fetch_video_statuses([item['video_id'] for item in candidates])
        defer_weak_backlog = False
        if reorder and self.defer_weak_backlog and self.publish_catchup_queue_threshold > 0:
            try:
                defer_weak_backlog = self._future_scheduled_queue_count(queue) >= self.publish_catchup_queue_threshold
            except Exception:
                defer_weak_backlog = False
        if reorder:
            for item in candidates:
                video = statuses.get(item.get('video_id')) or {}
                title = (video.get('snippet') or {}).get('title') or ''
                score = self._score_video_title(title, item.get('today'))
                if score <= 0:
                    try:
                        score = self._score_homer(item.get('homer_num'), item.get('today'))
                    except Exception:
                        score = item.get('priority_score') or 0
                item['priority_score'] = score
                item['_defer_to_normal_window'] = bool(
                    defer_weak_backlog and score < self.publish_backlog_min_score
                )
            candidates.sort(
                key=lambda item: (
                    1 if item.get('_defer_to_normal_window') else 0,
                    -(item.get('priority_score') or 0),
                    item.get('publish_at') or '',
                    item.get('key') or '',
                )
            )
        slot_queue = self._new_slot_queue()
        for item in protected_slots:
            slot_queue['items'][item.get('key') or item.get('video_id')] = {
                'publish_at': item.get('publish_at'),
                'status': 'reserved',
            }
        updates = []

        for item in candidates:
            video = statuses.get(item['video_id'])
            if not video:
                item['reschedule_status'] = 'missing_on_youtube'
                continue

            status = video.get('status', {})
            reported_publish_at = status.get('publishAt')
            current_publish_at = reported_publish_at or item.get('publish_at')
            recent_age = self._recent_reschedule_age_minutes(item)
            if (
                reported_publish_at
                and item.get('publish_at')
                and reported_publish_at != item.get('publish_at')
                and recent_age is not None
                and recent_age < 60
            ):
                current_publish_at = item.get('publish_at')
                item['reschedule_status'] = 'awaiting_youtube_consistency'
            privacy = status.get('privacyStatus')
            if privacy != 'private' or not current_publish_at:
                item['reschedule_status'] = 'not_private_scheduled'
                continue

            if item.get('_defer_to_normal_window'):
                new_publish_at = self._next_publish_slot(
                    slot_queue,
                    window_start_hour=self.publish_normal_window_start_hour,
                    window_end_hour=self.publish_normal_window_end_hour,
                )
            else:
                new_publish_at = self._next_publish_slot(slot_queue)
            slot_queue['items'][item['key']] = {
                'publish_at': new_publish_at,
                'status': 'reserved',
            }

            try:
                current_dt = datetime.fromisoformat(current_publish_at.replace('Z', '+00:00'))
                new_dt = datetime.fromisoformat(new_publish_at.replace('Z', '+00:00'))
                if not reorder and new_dt >= current_dt - timedelta(seconds=60):
                    item['reschedule_status'] = 'already_tight'
                    continue
                if reorder and abs((new_dt - current_dt).total_seconds()) < 300:
                    item['reschedule_status'] = 'already_tight'
                    continue
            except Exception:
                pass

            updates.append({
                'key': item.get('key'),
                'video_id': item['video_id'],
                'title': video.get('snippet', {}).get('title', ''),
                'old_publish_at': current_publish_at,
                'new_publish_at': new_publish_at,
                'priority_score': item.get('priority_score') or 0,
                'defer_to_normal_window': bool(item.get('_defer_to_normal_window')),
                'current_status': status,
            })

        for update in updates:
            reason = " defer=normal-window" if update.get('defer_to_normal_window') else ""
            print(
                f"{update['key']} {update['video_id']}: "
                f"{update['old_publish_at']} -> {update['new_publish_at']} "
                f"score={update['priority_score']}{reason} "
                f"{'(dry-run)' if dry_run else ''}"
            )
            if dry_run:
                continue
            body = self._status_update_body(
                update['video_id'],
                update['current_status'],
                update['new_publish_at'],
            )
            try:
                self.youtube.videos().update(part='status', body=body).execute()
            except Exception as e:
                update['success'] = False
                update['error'] = str(e)
                item = queue.get('items', {}).get(update['key'])
                if item:
                    item['reschedule_status'] = 'failed'
                    item['last_reschedule_error'] = str(e)
                    item['last_reschedule_attempted_at'] = self._utc_now().isoformat()
                    self._save_queue(queue)
                print(f"❌ Reschedule failed for {update['video_id']}: {e}")
                continue

            item = queue.get('items', {}).get(update['key'])
            if item:
                item['publish_at'] = update['new_publish_at']
                item['rescheduled_at'] = self._utc_now().isoformat()
                item['reschedule_status'] = 'weak_backlog_deferred' if update.get('defer_to_normal_window') else 'updated'
                update['success'] = True
                self._save_queue(queue)

        if not dry_run:
            self._save_queue(queue)

        return updates

    def upload_homer_video(self, homer_num, today=None, publish_at=None):
        """Upload a specific home run compilation (upload-once ledger enforced)."""
        if today is None:
            today = datetime.now().strftime('%Y-%m-%d')
        
        # Find the compiled video (prefer Shorts_Ready)
        candidates = [
            str(BASE_DIR / f"Shorts_Ready/Homer_{homer_num}_{today}_SHORT.mp4"),
            str(BASE_DIR / f"YouTube_Shorts_Ready/Homer_{homer_num}_{today}.mp4"),
            str(BASE_DIR / f"YouTube_Shorts_Ready/Homer_{homer_num}_{today}_SHORT.mp4")
        ]
        video_path = next((p for p in candidates if os.path.exists(p)), None)
        
        if not video_path:
            print(f"❌ Video not found for homer #{homer_num} on {today}")
            return None
        
        # Upload-once check
        led = self._load_ledger()
        key = f"{today}:{homer_num}"
        if led.get(key):
            print(f"⏭️  Skipping homer #{homer_num} (already uploaded as {led[key].get('video_id')})")
            return {'success': True, 'skipped': True, 'video_id': led[key].get('video_id')}

        ready, reason = self._source_post_status(homer_num, today)
        if not ready:
            print(f"🛑 Skipping homer #{homer_num}: source post is not upload-ready ({reason})")
            return {'success': False, 'skipped': True, 'error': reason}

        print(f"🏠 Uploading Home Run #{homer_num}")
        if publish_at:
            print(f"🗓️  Scheduled publish time: {publish_at}")
        
        # Create metadata
        metadata = self.create_video_metadata(
            homer_num,
            video_path,
            today,
            privacy='private' if publish_at else None,
            publish_at=publish_at,
        )
        
        # Upload the video
        res = self.upload_video(video_path, metadata)
        if res and res.get('success') and res.get('video_id'):
            led[key] = {'video_id': res['video_id'], 'uploaded_at': datetime.now().isoformat(), 'title': metadata.get('title','')}
            self._save_ledger(led)
            res['title'] = metadata.get('title', '')
        return res
    
    def update_video_metadata(self, video_id: str, metadata: dict):
        """Update title/description/tags of an already-uploaded video."""
        try:
            title = metadata.get('title', '').strip()
            # Ensure #Shorts in title when appropriate
            if '#Shorts' not in title:
                title = (title + ' #Shorts').strip()
            body = {
                'id': video_id,
                'snippet': {
                    'title': title,
                    'description': metadata.get('description', ''),
                    'tags': metadata.get('tags', []),
                    'categoryId': metadata.get('category', '17')
                },
                'status': {
                    'privacyStatus': metadata.get('privacy', 'public'),
                    'selfDeclaredMadeForKids': False
                }
            }
            self.youtube.videos().update(part='snippet,status', body=body).execute()
            print(f"🖊️  Updated metadata for video {video_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to update metadata: {e}")
            return False

    def upload_all_homers(self, today=None):
        """Upload all compiled home run videos (upload-once ledger enforced)."""
        if today is None:
            today = datetime.now().strftime('%Y-%m-%d')

        if not self._is_scheduled_publish_enabled():
            discovered = self._discover_compiled_homers(today)
            if not discovered:
                print(f"❌ No compiled videos found for {today}")
                return []

            led = self._load_ledger()
            print(f"🎬 UPLOADING {len(discovered)} HOME RUN VIDEOS TO YOUTUBE")
            print("📣 Immediate publishing enabled")
            print("=" * 60)

            results = []
            for homer_num in sorted(discovered.keys(), key=lambda x: (self._parse_float(x) or 0.0, x)):
                key = self._queue_key(today, homer_num)
                if led.get(key):
                    print(f"⏭️  Skipping homer #{homer_num} (already uploaded as {led[key].get('video_id')})")
                    results.append({'success': True, 'skipped': True, 'video_id': led[key].get('video_id')})
                    print("")
                    continue
                result = self.upload_homer_video(homer_num, today)
                if result:
                    results.append(result)
                print("")

            successful_uploads = sum(1 for r in results if r.get('success') and not r.get('skipped'))
            print(f"🎉 UPLOAD COMPLETE!")
            print(f"✅ Successfully uploaded: {successful_uploads}/{len([r for r in results if not r.get('skipped')])}")
            print(f"⏭️  Skipped (already uploaded): {sum(1 for r in results if r.get('skipped'))}")
            print(f"❌ Failed uploads: {sum(1 for r in results if not r.get('success'))}")
            return results

        queue = self._sync_queue_for_today(today)
        queue_items = self._queue_items_sorted(queue)

        if not queue_items:
            print(f"❌ No compiled videos found for {today}")
            return []

        led = self._load_ledger()
        print(f"🎬 UPLOADING {len(queue_items)} HOME RUN VIDEOS TO YOUTUBE")
        if self._is_scheduled_publish_enabled():
            max_day_label = self.publish_max_per_day if self.publish_max_per_day > 0 else "unlimited"
            print(
                "🗓️  Scheduled publishing enabled "
                f"(window {self.publish_window_start_hour}:00-{self.publish_window_end_hour}:00 ET, "
                f"start delay {self.publish_start_delay_minutes} min, gap {self.publish_gap_minutes} min, "
                f"max/day {max_day_label}, horizon {self.publish_max_horizon_days}d, "
                f"queue cap {self.publish_max_queue_items})"
            )
        else:
            print("📣 Immediate publishing enabled")
        print("=" * 60)
        
        results = []
        for item in queue_items:
            homer_num = item.get('homer_num')
            key = item.get('key') or self._queue_key(today, homer_num)
            publish_at = item.get('publish_at')
            video_path = item.get('video_path')

            if led.get(key):
                print(f"⏭️  Skipping homer #{homer_num} (already uploaded as {led[key].get('video_id')})")
                item['status'] = 'uploaded'
                item['video_id'] = led[key].get('video_id')
                results.append({'success': True, 'skipped': True, 'video_id': led[key].get('video_id')})
                print("")
                continue

            if not video_path or not os.path.exists(video_path):
                print(f"❌ Video not found for homer #{homer_num} at {video_path}")
                item['status'] = 'missing'
                results.append({'success': False, 'error': 'video_missing'})
                print("")
                continue

            if self._is_scheduled_publish_enabled() and not publish_at:
                publish_at = self._next_publish_slot(queue)
                item['publish_at'] = publish_at

            print(f"📦 Queue slot: {publish_at}")
            result = self.upload_homer_video(homer_num, today, publish_at=publish_at)
            if result:
                results.append(result)
                if result.get('success') and result.get('video_id'):
                    item['status'] = 'uploaded'
                    item['video_id'] = result['video_id']
                    item['uploaded_at'] = self._utc_now().isoformat()
                    led[key] = {
                        'video_id': result['video_id'],
                        'uploaded_at': item['uploaded_at'],
                        'title': item.get('title') or result.get('title', '')
                    }
                    self._save_ledger(led)
                else:
                    item['status'] = 'failed'
                    item['last_error'] = result.get('error', 'upload_failed')
            print("")  # Add spacing

        self._save_queue(queue)
        
        successful_uploads = sum(1 for r in results if r.get('success') and not r.get('skipped'))
        
        print(f"🎉 UPLOAD COMPLETE!")
        print(f"✅ Successfully uploaded: {successful_uploads}/{len([r for r in results if not r.get('skipped')])}")
        print(f"⏭️  Skipped (already uploaded): {sum(1 for r in results if r.get('skipped'))}")
        print(f"❌ Failed uploads: {sum(1 for r in results if not r.get('success'))}")
        
        return results

def main():
    parser = argparse.ArgumentParser(description="Upload MLB home run compilations to YouTube.")
    parser.add_argument("date", nargs="?", help="Date to upload (YYYY-MM-DD)")
    parser.add_argument("--reauth", "--force-reauth", dest="reauth", action="store_true", help="Force a fresh browser OAuth sign-in and exit")
    args = parser.parse_args()
    date_arg = args.date

    print("🎬 YOUTUBE HOME RUN BOT 🎬")
    print("==========================")
    print("📤 Automatically uploads MLB home run compilations to YouTube")
    print("💰 100% FREE with generous API quotas!")
    print("")
    
    # Check if credentials file exists
    if not os.path.exists(str(BASE_DIR / 'config' / 'youtube_credentials.json')):
        print("⚠️  YouTube API setup required!")
        print("")
        print("📋 Quick Setup Guide:")
        print("1. Go to: https://console.developers.google.com/")
        print("2. Create project or select existing")
        print("3. Enable 'YouTube Data API v3'")
        print("4. Create OAuth 2.0 credentials")
        print("5. Download JSON file as 'youtube_credentials.json'")
        print("")
        print("💡 This is completely free and takes ~5 minutes!")
        return
    
    # Initialize bot
    if args.reauth:
        bot = YouTubeHomeRunBot(force_reauth=True)
        if not hasattr(bot, 'youtube') or not bot.youtube:
            return
        print("✅ YouTube OAuth reauth complete.")
        return

    bot = YouTubeHomeRunBot()
    
    if not hasattr(bot, 'youtube') or not bot.youtube:
        return
    
    print("")
    print(f"Date: {date_arg or datetime.now().strftime('%Y-%m-%d')}")
    print("Choose an option:")
    print("1. Upload all compiled home runs")
    print("2. Upload specific home run")
    print("3. Test upload with one video")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        results = bot.upload_all_homers(date_arg)
        successful = sum(1 for r in results if r['success'])
        print(f"\n🎉 Uploaded {successful} videos to YouTube!")
        
    elif choice == "2":
        homer_num = input("Enter home run number: ").strip()
        result = bot.upload_homer_video(homer_num, date_arg)
        if result and result['success']:
            print(f"\n🎉 Video uploaded successfully!")
            print(f"🔗 URL: {result['url']}")
            
    elif choice == "3":
        # Find the first compiled video to test with
        video_files = glob.glob(str(BASE_DIR / "Shorts_Ready/Homer_*_SHORT.mp4")) or glob.glob(str(BASE_DIR / "YouTube_Shorts_Ready/Homer_*.mp4"))
        if video_files:
            video_file = sorted(video_files)[0]
            match = re.search(r'Homer_(\d+)_', os.path.basename(video_file))
            if match:
                test_homer = match.group(1)
                print(f"🧪 Testing upload with home run #{test_homer}")
                result = bot.upload_homer_video(test_homer, date_arg)
                if result and result['success']:
                    print(f"\n🎉 Test upload successful!")
                    print(f"🔗 URL: {result['url']}")
            else:
                print("❌ Could not parse video filename!")
        else:
            print("❌ No compiled videos found for testing!")
    else:
        print("❌ Invalid choice!")

if __name__ == "__main__":
    main()
