#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
YouTube Home Run Bot - Automatically uploads MLB home run compilations to YouTube
100% FREE to use with generous quotas!
"""

import os
import glob
import re
from datetime import datetime
import json
from pathlib import Path
import subprocess

# YouTube API imports
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import urllib.request, json as jsonlib, os

BASE_DIR = Path(__file__).resolve().parent

class YouTubeHomeRunBot:
    def __init__(self):
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
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        print("🎬 YouTube Home Run Bot initialized!")
        
        # Authenticate with YouTube API
        self.youtube = self.authenticate()
        if not self.youtube:
            print("❌ Failed to authenticate with YouTube API")
            return
        
        print("✅ YouTube API authenticated successfully!")
    
    def authenticate(self):
        """Authenticate with YouTube API"""
        credentials = None
        
        # Load existing token
        if os.path.exists(self.token_file):
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
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes
                )
                # Use an ephemeral local port for OAuth to avoid conflicts under cron
                credentials = flow.run_local_server(port=0, open_browser=True,
                                                   authorization_prompt_message='Please authorize access to upload to your YouTube channel.',
                                                   success_message='Authentication complete. You can close this tab and return to the terminal.')
            
            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(credentials.to_json())
        
        try:
            return build(self.api_service_name, self.api_version, credentials=credentials)
        except Exception as e:
            print(f"❌ Failed to build YouTube service: {e}")
            return None
    
    def extract_homer_info(self, homer_num, today=None):
        """Extract batter and enriched stats for metadata"""
        if today is None:
            today = datetime.now().strftime('%Y-%m-%d')
        
        posts_dir = str(BASE_DIR / 'MLB_HomeRun_Posts' / today)
        post_pattern = f"{posts_dir}/tonights_homer_{homer_num}_*.txt"
        post_files = glob.glob(post_pattern)
        # Fallback: search archived folders if live post is missing
        if not post_files:
            post_files = sorted(glob.glob(f"{posts_dir}/_archived_*/tonights_homer_{homer_num}_*.txt"))
        
        # Additional fallback: if compiled ID is a simple index (e.g., 11) and no direct match,
        # use the same enumeration order the downloader used (sorted post files, 1-indexed)
        if not post_files and re.fullmatch(r"\d+", str(homer_num)):
            all_posts = sorted(glob.glob(f"{posts_dir}/tonights_homer_*_*.txt"))
            try:
                idx = int(homer_num)
                if 1 <= idx <= len(all_posts):
                    post_files = [all_posts[idx - 1]]
            except Exception:
                pass
        
        default_info = {
            'batter': 'MLB Player',
            'team': 'MLB',
            'distance': '',
            'launch_speed': '',
            'launch_angle': '',
            'description': 'Amazing MLB home run!'
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
                    m = re.search(r"tonights_homer_([0-9]+(?:-[0-9]+)?)_", os.path.basename(post_files[0]))
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
                    info['description'] = ' '.join(caption_lines)
            except Exception as e:
                print(f"⚠️  Could not read post file: {e}")
        
        return info
    
    def create_video_metadata(self, homer_num, video_path, today=None):
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
        
        # Final description (2 lines + hashtags)
        description = "\n".join([x for x in [line1, line2] if x])
        if hashtags_line:
            description += ("\n" if description else "") + hashtags_line
        
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
            'privacy': 'public',
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
        import re as _re
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
        """Send an iMessage notification via AppleScript if HOMER_NOTIFY_PHONE is set.
        Returns True on success, False otherwise.
        """
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

    def upload_homer_video(self, homer_num, today=None):
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

        print(f"🏠 Uploading Home Run #{homer_num}")
        
        # Create metadata
        metadata = self.create_video_metadata(homer_num, video_path, today)
        
        # Upload the video
        res = self.upload_video(video_path, metadata)
        if res and res.get('success') and res.get('video_id'):
            led[key] = {'video_id': res['video_id'], 'uploaded_at': datetime.now().isoformat(), 'title': metadata.get('title','')}
            self._save_ledger(led)
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
        
        # Find all compiled videos (prefer Shorts_Ready)
        video_files = sorted(glob.glob(str(BASE_DIR / f"Shorts_Ready/Homer_*_{today}_SHORT.mp4")))
        if not video_files:
            video_files = sorted(glob.glob(str(BASE_DIR / f"YouTube_Shorts_Ready/Homer_*_{today}.mp4")))
        
        if not video_files:
            print(f"❌ No compiled videos found for {today}")
            return []
        
        led = self._load_ledger()
        print(f"🎬 UPLOADING {len(video_files)} HOME RUN VIDEOS TO YOUTUBE")
        print("=" * 60)
        
        results = []
        
        for video_file in sorted(video_files):
            # Extract homer number from filename
            match = re.search(r'Homer_([0-9]+(?:-[0-9]+)?)_', os.path.basename(video_file))
            if match:
                homer_num = match.group(1)
                key = f"{today}:{homer_num}"
                if led.get(key):
                    print(f"⏭️  Skipping homer #{homer_num} (already uploaded as {led[key].get('video_id')})")
                    results.append({'success': True, 'skipped': True, 'video_id': led[key].get('video_id')})
                    print("")
                    continue
                result = self.upload_homer_video(homer_num, today)
                if result:
                    results.append(result)
                print("")  # Add spacing
        
        successful_uploads = sum(1 for r in results if r.get('success') and not r.get('skipped'))
        
        print(f"🎉 UPLOAD COMPLETE!")
        print(f"✅ Successfully uploaded: {successful_uploads}/{len([r for r in results if not r.get('skipped')])}")
        print(f"⏭️  Skipped (already uploaded): {sum(1 for r in results if r.get('skipped'))}")
        print(f"❌ Failed uploads: {sum(1 for r in results if not r.get('success'))}")
        
        return results

def main():
    import sys
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None

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
