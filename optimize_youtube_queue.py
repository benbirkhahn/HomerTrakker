#!/usr/bin/env python3
"""Refresh performance data and optimize future scheduled YouTube posts."""

import argparse

import youtube_performance_sync
from youtube_homer_bot import YouTubeHomeRunBot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply schedule changes to YouTube.")
    parser.add_argument(
        "--no-reorder",
        action="store_true",
        help="Only tighten timing; do not reorder by current ranking score.",
    )
    parser.add_argument(
        "--min-lead-minutes",
        type=int,
        default=None,
        help="Do not reschedule videos this close to publish time.",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not optimize future scheduled video titles/tags.",
    )
    args = parser.parse_args()

    youtube_performance_sync.main([])

    bot = YouTubeHomeRunBot()
    if not getattr(bot, "youtube", None):
        raise SystemExit("YouTube authentication is not available.")

    updates = bot.reschedule_pending_posts(
        dry_run=not args.apply,
        reorder=not args.no_reorder,
        min_lead_minutes=args.min_lead_minutes,
    )
    metadata_updates = []
    if not args.no_metadata:
        metadata_updates = bot.optimize_scheduled_metadata(
            dry_run=not args.apply,
            min_lead_minutes=args.min_lead_minutes,
        )
    action = "Updated" if args.apply else "Would update"
    print(f"{action} {len(updates)} scheduled video(s).")
    if not args.no_metadata:
        print(f"{action} metadata on {len(metadata_updates)} scheduled video(s).")


if __name__ == "__main__":
    main()
