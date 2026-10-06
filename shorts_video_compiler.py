#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
Shorts Video Compiler (FFmpeg-based)
- Converts landscape clips to 9:16 vertical with blurred background
- Concatenates angles per home run
- Enforces <= 60s total duration for YouTube Shorts
"""

import subprocess
import os
import re
import json
import glob
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = str(Path(__file__).resolve().parent)

from homer_timing_logger import timing_logger


def load_local_env(path=Path(BASE_DIR) / '.homer.env'):
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


class ShortsCompiler:
    BROADCAST_MAX_SECS = float(os.getenv('HOMER_BROADCAST_MAX_SECS', '15'))
    TOTAL_MAX_SECS = float(os.getenv('HOMER_TOTAL_MAX_SECS', '30'))
    TRANSCODE_TIMEOUT = float(os.getenv('HOMER_TRANSCODE_TIMEOUT_SECS', os.getenv('HOMER_FALLBACK_TIMEOUT', '180')))
    CONCAT_TIMEOUT = float(os.getenv('HOMER_CONCAT_TIMEOUT_SECS', '120'))

    def __init__(self, date_str=None, open_ui=False, require_both=None):
        self.today = date_str or datetime.now().strftime('%Y-%m-%d')
        self.videos_dir = os.path.join(BASE_DIR, "MLB_HomeRun_Posts", self.today, "videos")
        self.out_dir = os.path.join(BASE_DIR, "Shorts_Ready")
        import os as _os
        self.temp_dir = os.path.join(self.out_dir, f"temp_{_os.getpid()}")
        self.open_ui = open_ui
        # Prefer explicit flag when provided; otherwise use env
        self.require_both = (bool(require_both) if require_both is not None else (os.getenv('HOMER_REQUIRE_BOTH') == '1'))
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        print(f"🎬 Shorts Compiler ready for {self.today}")

    def ffprobe_duration(self, path):
        try:
            r = subprocess.run([
                'ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1', path
            ], capture_output=True, text=True)
            return float(r.stdout.strip())
        except:
            return 0.0

    def expected_output_duration(self, broadcast_path, animated_path):
        broadcast_duration = self.ffprobe_duration(broadcast_path) if broadcast_path else 0.0
        animated_duration = self.ffprobe_duration(animated_path) if animated_path else 0.0
        broadcast_use = min(broadcast_duration, self.BROADCAST_MAX_SECS)
        animated_budget = max(0.0, self.TOTAL_MAX_SECS - broadcast_use)
        animated_use = min(animated_duration, animated_budget)
        return broadcast_use + animated_use

    def make_vertical(self, in_path, out_path, max_seconds=None):
        # Create vertical 1080x1920 with blurred background (safer boxblur)
        fc = (
            "[0:v]split=2[bgsrc][fgsrc];"
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:1[bg];"
            "[fgsrc]scale=1080:-1:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
        )
        cmd = ['ffmpeg', '-y']
        # Limit decoding before the expensive scale/blur filter.  The old flow
        # transcoded an entire source clip and only trimmed afterward, which
        # made otherwise valid highlights hit the automation timeout.
        if max_seconds and max_seconds > 0:
            cmd += ['-t', str(max_seconds)]
        cmd += [
            '-i', in_path,
            '-filter_complex', ''.join(fc),
            '-r','30','-c:v','libx264','-preset','veryfast','-crf','23',
            '-c:a','aac','-ar','48000','-ac','2','-b:a','128k',
            '-movflags','+faststart', out_path
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=self.TRANSCODE_TIMEOUT)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg transcode failed: {in_path} -> {out_path}")
            if e.stderr:
                print(e.stderr.strip()[:4000])
            else:
                print("No ffmpeg stderr captured.")
            return False
        except subprocess.TimeoutExpired:
            print(f"⏱️  FFmpeg transcode timed out after {self.TRANSCODE_TIMEOUT:.0f}s: {in_path} -> {out_path}")
            return False

    def trim_clip(self, in_path, out_path, seconds):
        try:
            subprocess.run([
                'ffmpeg','-y','-i', in_path,'-t', str(seconds), '-c','copy', out_path
            ], check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg trim failed: {in_path} -> {out_path} (t={seconds}s)")
            if e.stderr:
                print(e.stderr.strip()[:4000])
            return False

    def compile_homer(self, homer_num):
        print(f"🏠 Compile homer #{homer_num}")
        out_path = os.path.join(self.out_dir, f"Homer_{homer_num}_{self.today}_SHORT.mp4")
        pattern = os.path.join(self.videos_dir, f"homer_{homer_num}_*.mp4")
        files = sorted(glob.glob(pattern))
        # Skip produced_* clips by default unless explicitly allowed
        allow_produced = os.getenv('HOMER_ALLOW_PRODUCED') == '1'
        if not allow_produced:
            before = len(files)
            files = [f for f in files if 'produced_' not in os.path.basename(f)]
            if before and not files:
                print("⚠️ Only produced clips found; produced is disabled. Skipping.")
        if not files:
            print("❌ No source clips")
            return None

        # Partition into broadcast (diamond) vs animated (darkroom)
        broadcast_files = [f for f in files if 'animated_' not in os.path.basename(f)]
        animated_files = [f for f in files if 'animated_' in os.path.basename(f)]

        # Prefer a single broadcast with 4000K if present
        def pick_broadcast(fs):
            for f in fs:
                if '4000K' in os.path.basename(f):
                    return f
            return fs[0] if fs else None
        b = pick_broadcast(broadcast_files)
        a = animated_files[0] if animated_files else None

        selected = [p for p in [b, a] if p]
        # Extract homer number for logging
        match = re.search(r'homer_(\d+)', os.path.basename(files[0]))
        at_bat_index = int(match.group(1)) if match else 0
        
        # Record clip arrival in timing log
        if b:
            timing_logger.record_clip_arrival(str(homer_num), at_bat_index, 'broadcast')
        if a:
            timing_logger.record_clip_arrival(str(homer_num), at_bat_index, 'animated')
        
        if self.require_both:
            if not (b and a):
                timing_logger.record_timeout(str(homer_num), at_bat_index)
                missing = "animated" if b else "broadcast"
                print(f"⏭️  Skipping compile: missing {missing} clip and both angles are required (HOMER_REQUIRE_BOTH=1)")
                return None
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                existing_duration = self.ffprobe_duration(out_path)
                expected_duration = self.expected_output_duration(b, a)
                if existing_duration >= max(1.0, expected_duration - 1.5):
                    print(f"⏭️  Already compiled with both required angles: {out_path}")
                    return out_path
                print(
                    "♻️  Rebuilding existing output; duration is too short for both "
                    f"required angles ({existing_duration:.1f}s < expected {expected_duration:.1f}s): {out_path}"
                )
                try:
                    os.remove(out_path)
                except OSError as e:
                    print(f"❌ Could not replace existing output: {e}")
                    return None
        elif os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"⏭️  Already compiled: {out_path}")
            return out_path
        if not selected:
            print("❌ Nothing selected")
            return None

        processed = []
        processed_roles = []
        total = 0.0
        for idx, path in enumerate(selected, 1):
            role = 'animated' if 'animated_' in os.path.basename(path) else 'broadcast'
            base = os.path.basename(path)
            v_out = os.path.join(self.temp_dir, f"{homer_num}_{idx}_v.mp4")
            max_seconds = (
                self.BROADCAST_MAX_SECS
                if role == 'broadcast'
                else max(0.0, self.TOTAL_MAX_SECS - self.BROADCAST_MAX_SECS)
            )
            ok = self.make_vertical(path, v_out, max_seconds=max_seconds)
            if not ok:
                print(f"⏭️  Skipping angle due to ffmpeg error: {base}")
                if self.require_both:
                    print(f"🛑 Aborting compile: required {role} angle failed")
                    return None
                continue
            dur = self.ffprobe_duration(v_out)
            if idx == 1:  # broadcast segment cap
                allowed = self.BROADCAST_MAX_SECS
            else:         # animated segment fills up to TOTAL_MAX_SECS
                allowed = max(0.0, self.TOTAL_MAX_SECS - total)
            use = min(dur, allowed)
            if use <= 0.9:
                continue
            if use < dur - 0.1:
                trimmed = os.path.join(self.temp_dir, f"{homer_num}_{idx}_trim.mp4")
                if self.trim_clip(v_out, trimmed, use):
                    processed.append(trimmed)
                    processed_roles.append(role)
                else:
                    print(f"⏭️  Skipping trimmed segment due to ffmpeg error: {os.path.basename(v_out)}")
                    if self.require_both:
                        print(f"🛑 Aborting compile: required {role} angle failed during trim")
                        return None
                    continue
            else:
                processed.append(v_out)
                processed_roles.append(role)
            total += use
            if total >= self.TOTAL_MAX_SECS - 0.5:
                break

        if self.require_both and not {'broadcast', 'animated'}.issubset(set(processed_roles)):
            missing_roles = sorted({'broadcast', 'animated'} - set(processed_roles))
            print(f"🛑 Aborting compile: missing processed required angle(s): {', '.join(missing_roles)}")
            return None

        if not processed:
            print("❌ Nothing processed")
            return None
        list_file = os.path.join(self.temp_dir, f"list_{homer_num}.txt")
        with open(list_file,'w') as f:
            for p in processed:
                f.write(f"file '{os.path.abspath(p)}'\n")
        try:
            tmp_out_path = os.path.join(self.temp_dir, f"out_{homer_num}.mp4")
            subprocess.run([
                'ffmpeg','-y','-f','concat','-safe','0','-i', list_file,
                '-fflags','+genpts',
                '-c:v','libx264','-preset','veryfast','-crf','23',
                '-c:a','aac','-ar','48000','-ac','2','-b:a','128k',
                '-movflags','+faststart', tmp_out_path
            ], check=True, capture_output=True, timeout=self.CONCAT_TIMEOUT)
            shutil.move(tmp_out_path, out_path)
            print(f"✅ Created: {out_path}")
            return out_path
        except subprocess.TimeoutExpired:
            print(f"⏱️  FFmpeg concat timed out after {self.CONCAT_TIMEOUT:.0f}s for {homer_num}")
            return None

    def compile_all(self):
        if not os.path.exists(self.videos_dir):
            print(f"❌ Not found: {self.videos_dir}")
            return []
        # Determine homers present
        homer_nums = set()
        for p in glob.glob(os.path.join(self.videos_dir, 'homer_*.mp4')):
            m = re.search(r"homer_([A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)_", os.path.basename(p))
            if m:
                homer_nums.add(m.group(1))
        out = []
        for num in sorted(homer_nums):
            path = self.compile_homer(num)
            if path:
                out.append(path)
        print(f"🎉 Shorts built: {len(out)}")
        # Cleanup temp working files to save space
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"⚠️  Could not clean temp dir: {e}")
        
        # Optionally open the output folder (off by default for automation)
        import os as _os
        if self.open_ui or _os.getenv('HOMER_OPEN_FOLDERS') == '1':
            _os.system(f'open "{self.out_dir}"')
        
        return out


def main():
    import sys, argparse
    print("📱 SHORTS VIDEO COMPILER")
    print("========================")
    parser = argparse.ArgumentParser()
    parser.add_argument('date', nargs='?', default=None)
    parser.add_argument('--open', dest='open_ui', action='store_true', help='Open output folder when done')
    parser.add_argument('--require-both', dest='require_both', action='store_true', help='Require broadcast+animated to compile a short')
    args = parser.parse_args()
    sc = ShortsCompiler(args.date, open_ui=args.open_ui, require_both=args.require_both)
    sc.compile_all()
if __name__ == '__main__':
    main()
