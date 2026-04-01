#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
Run Date Pipeline
Runs the full HomerTrakker pipeline for a specific date:
- Statcast enrich
- Download videos (with optional animated retry)
- Compile Shorts (optionally require broadcast+animated)
- Upload to YouTube (optionally upload-only scopes)

Usage examples:
  ./run_date_pipeline.py 2025-09-27 --require-both --retry-animated --upload
  ./run_date_pipeline.py yesterday --require-both --retry-animated --upload
  ./run_date_pipeline.py 2025-09-27 --require-both --no-upload
"""

import argparse
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PY = "/Users/benbirkhahn/twitter_bot_env/bin/python3"


def resolve_date(s: str) -> str:
    s = (s or '').strip().lower()
    if not s or s == 'today':
        return datetime.now().strftime('%Y-%m-%d')
    if s == 'yesterday':
        return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    # Assume YYYY-MM-DD
    return s


def run(cmd: list[str], env: dict | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env or os.environ.copy())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('date', help="YYYY-MM-DD | today | yesterday")
    ap.add_argument('--require-both', action='store_true', help='Require broadcast+animated to compile')
    ap.add_argument('--retry-animated', action='store_true', help='Retry downloading delayed animated clips')
    ap.add_argument('--retry-count', type=int, default=3)
    ap.add_argument('--retry-delay', type=int, default=2, help='Minutes between animated retries')
    ap.add_argument('--upload', dest='upload', action='store_true', help='Upload to YouTube when done')
    ap.add_argument('--no-upload', dest='upload', action='store_false')
    ap.set_defaults(upload=True)
    ap.add_argument('--open', dest='open_ui', action='store_true', help='Open output folders when done')
    ap.add_argument('--yt-minimal', action='store_true', help='Use upload-only OAuth scope (no metadata updates)')
    args = ap.parse_args()

    date = resolve_date(args.date)

    # Base environment
    env = os.environ.copy()
    env['HOMER_REQUIRE_BOTH'] = '1' if args.require_both else '0'
    if args.retry_animated:
        env['HOMER_RETRY_ANIMATED'] = '1'
        env['HOMER_RETRY_COUNT'] = str(args.retry_count)
        env['HOMER_RETRY_DELAY'] = str(args.retry_delay)
    if args.open_ui:
        env['HOMER_OPEN_FOLDERS'] = '1'
    if args.yt_minimal:
        env['HOMER_YT_MINIMAL_SCOPES'] = '1'

    print("\n=== RUN DATE PIPELINE ===")
    print(f"Date: {date}")
    print(f"Require both: {'ON' if args.require_both else 'OFF'}")
    print(f"Retry animated: {'ON' if args.retry_animated else 'OFF'} (count={args.retry_count}, delay={args.retry_delay}m)")
    print(f"Upload: {'ON' if args.upload else 'OFF'}")
    print(f"YouTube minimal scopes: {'ON' if args.yt_minimal else 'OFF'}")
    print("")

    # 1) Statcast
    run([PY, str(BASE_DIR / 'statcast_enricher.py'), date], env)

    # 2) Downloads
    dl_cmd = [PY, str(BASE_DIR / 'download_homer_videos.py'), date]
    if args.retry_animated:
        dl_cmd += ['--retry-animated', '--retry-count', str(args.retry_count), '--retry-delay', str(args.retry_delay)]
    run(dl_cmd, env)

    # 3) Compile
    # Use CLI flag to avoid relying solely on env
    run([PY, str(BASE_DIR / 'shorts_video_compiler.py'), date, '--require-both'] if args.require_both else [PY, str(BASE_DIR / 'shorts_video_compiler.py'), date], env)

    # 4) Upload (optional)
    if args.upload:
        run([PY, str(BASE_DIR / 'uploader_runner.py'), date], env)

    print("\n✅ Done.")


if __name__ == '__main__':
    main()
