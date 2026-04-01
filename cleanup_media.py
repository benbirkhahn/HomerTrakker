#!/Users/benbirkhahn/twitter_bot_env/bin/python3
"""
Cleanup media artifacts to free disk space.
- By default, removes source videos for a given date from MLB_HomeRun_Posts/<date>/videos
- Optionally can be extended for other paths.
"""

import os
import sys
import argparse
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def human_bytes(n: int) -> str:
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def cleanup_sources_for_date(date_str: str, delete_posts: bool=False) -> dict:
    # Allow temporarily disabling cleanup to avoid race conditions during manual reprocessing
    if os.getenv('HOMER_DISABLE_CLEANUP') == '1':
        print("⏭️  Skipping cleanup due to HOMER_DISABLE_CLEANUP=1")
        return {"deleted_files": 0, "freed_bytes": 0, "paths": []}
    sentinel = Path('/tmp') / f'homer_noclean_{date_str}'
    if sentinel.exists():
        print(f"⏭️  Skipping cleanup due to sentinel {sentinel}")
        return {"deleted_files": 0, "freed_bytes": 0, "paths": []}

    posts_dir = BASE_DIR / 'MLB_HomeRun_Posts' / date_str
    videos_dir = posts_dir / 'videos'
    stats_dir = posts_dir / 'stats'
    report = {"deleted_files": 0, "freed_bytes": 0, "paths": []}

    # Helper to delete files by pattern
    def delete_glob(folder: Path, pattern: str):
        deleted = 0
        freed = 0
        if not folder.exists():
            return deleted, freed
        for p in folder.glob(pattern):
            try:
                sz = p.stat().st_size if p.exists() else 0
                p.unlink()
                deleted += 1
                freed += sz
            except Exception as e:
                print(f"⚠️  Could not delete {p}: {e}")
        return deleted, freed

    # Delete source videos
    d, f = delete_glob(videos_dir, '*.mp4')
    report["deleted_files"] += d
    report["freed_bytes"] += f
    report["paths"].append(str(videos_dir))

    # Delete stat JSONs
    d, f = delete_glob(stats_dir, '*.json')
    report["deleted_files"] += d
    report["freed_bytes"] += f
    report["paths"].append(str(stats_dir))

    # Optionally delete post text files in the date root
    if delete_posts:
        d, f = delete_glob(posts_dir, 'tonights_homer_*.txt')
        report["deleted_files"] += d
        report["freed_bytes"] += f
        report["paths"].append(str(posts_dir))

    # Remove empty directories
    for folder in (videos_dir, stats_dir, posts_dir):
        try:
            if folder.exists() and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        except Exception:
            pass

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', help='Date (YYYY-MM-DD) to clean, e.g. 2025-09-18')
    parser.add_argument('--delete-posts', action='store_true', help='Also delete tonights_homer_*.txt')
    args = parser.parse_args()

    rep = cleanup_sources_for_date(args.date, delete_posts=args.delete_posts)
    print("🧹 Cleanup complete")
    for p in rep.get('paths', []):
        print(f"Path cleaned: {p}")
    print(f"Files deleted: {rep['deleted_files']}")
    print(f"Freed: {human_bytes(rep['freed_bytes'])}")

if __name__ == '__main__':
    main()
