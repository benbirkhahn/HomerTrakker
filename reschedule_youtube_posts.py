#!/usr/bin/env python3
"""Reschedule still-private YouTube Shorts using the current HomerTrakker queue policy."""

import argparse

from youtube_homer_bot import YouTubeHomeRunBot


def main():
    parser = argparse.ArgumentParser(
        description="Pull future private scheduled YouTube posts into the current queue spacing."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the new publishAt times to YouTube. Default is dry-run.",
    )
    parser.add_argument(
        "--reorder",
        action="store_true",
        help="Recompute priority scores and put stronger clips into earlier slots.",
    )
    args = parser.parse_args()

    bot = YouTubeHomeRunBot()
    if not getattr(bot, "youtube", None):
        raise SystemExit("YouTube authentication is not available.")

    updates = bot.reschedule_pending_posts(dry_run=not args.apply, reorder=args.reorder)
    action = "Updated" if args.apply else "Would update"
    print(f"{action} {len(updates)} scheduled video(s).")


if __name__ == "__main__":
    main()
