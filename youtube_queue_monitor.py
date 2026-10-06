#!/usr/bin/env python3
"""Throttled automatic optimizer for the scheduled YouTube queue."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.errors import HttpError

import youtube_performance_sync
from youtube_homer_bot import YouTubeHomeRunBot


STATE_DIR = Path.home() / ".homer"
STATE_PATH = STATE_DIR / "youtube_queue_monitor.json"
QUEUE_PATH = STATE_DIR / "youtube_queue.json"


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def load_state():
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text())
    except Exception:
        pass
    return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def queue_signature():
    queue = load_json(QUEUE_PATH, {"items": {}})
    items = []
    for key, item in sorted((queue.get("items") or {}).items()):
        items.append(
            {
                "key": key,
                "video_id": item.get("video_id"),
                "publish_at": item.get("publish_at"),
                "priority_score": item.get("priority_score"),
                "status": item.get("status"),
                "reschedule_status": item.get("reschedule_status"),
            }
        )
    return json.dumps(items, sort_keys=True, separators=(",", ":"))


def is_quota_error(exc):
    if isinstance(exc, HttpError):
        text = str(exc).lower()
        return "quota" in text or "quotaexceeded" in text
    return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply queue changes to YouTube.")
    parser.add_argument("--force", action="store_true", help="Ignore throttle interval.")
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=int(os.getenv("HOMER_YT_OPTIMIZE_INTERVAL_MINUTES", "30")),
        help="Minimum minutes between optimizer runs.",
    )
    parser.add_argument(
        "--min-lead-minutes",
        type=int,
        default=int(os.getenv("HOMER_YT_RESCHEDULE_MIN_LEAD_MINUTES", "10")),
        help="Do not reschedule videos this close to publish time.",
    )
    parser.add_argument("--no-reorder", action="store_true", help="Do not reorder by score.")
    parser.add_argument("--no-metadata", action="store_true", help="Do not optimize scheduled titles/tags.")
    parser.add_argument(
        "--quota-backoff-hours",
        type=float,
        default=float(os.getenv("HOMER_YT_QUOTA_BACKOFF_HOURS", "6")),
        help="Hours to skip nonessential optimizer API calls after quota errors.",
    )
    parser.add_argument(
        "--stable-skip-minutes",
        type=float,
        default=float(os.getenv("HOMER_YT_STABLE_SKIP_MINUTES", "120")),
        help="Skip API optimizer work this long when the local queue is unchanged and last full run was clean.",
    )
    parser.add_argument(
        "--performance-max-age-minutes",
        type=float,
        default=float(os.getenv("HOMER_YT_PERFORMANCE_SYNC_MAX_AGE_MINUTES", "180")),
        help="Use cached performance summary if it is this fresh.",
    )
    parser.add_argument(
        "--quota-recovery-stable-minutes",
        type=float,
        default=float(os.getenv("HOMER_YT_QUOTA_RECOVERY_STABLE_MINUTES", "120")),
        help="After quota backoff expires, keep skipping this long if the local queue did not change.",
    )
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    state = load_state()
    current_queue_signature = queue_signature()
    quota_blocked_until = parse_dt(state.get("quota_blocked_until"))
    if quota_blocked_until and now < quota_blocked_until:
        state["quota_backoff_queue_signature"] = current_queue_signature
        state["last_local_queue_seen_at"] = now.isoformat()
        save_state(state)
        remaining = round((quota_blocked_until - now).total_seconds() / 3600.0, 2)
        print(f"YouTube queue monitor skipped; API quota backoff active for {remaining} hour(s).")
        return []
    quota_recovery_skip_until = parse_dt(state.get("quota_recovery_skip_until"))
    if (
        quota_recovery_skip_until
        and now < quota_recovery_skip_until
        and state.get("quota_backoff_queue_signature") == current_queue_signature
    ):
        state["last_run_at"] = now.isoformat()
        state["last_quota_recovery_skip_at"] = now.isoformat()
        save_state(state)
        remaining = round((quota_recovery_skip_until - now).total_seconds() / 60.0, 1)
        print(f"YouTube queue monitor skipped; quota recovery stable window active for {remaining} min.")
        return []
    if (
        quota_blocked_until
        and now >= quota_blocked_until
        and args.quota_recovery_stable_minutes > 0
        and state.get("quota_backoff_queue_signature") == current_queue_signature
    ):
        state["quota_blocked_until"] = None
        state["quota_recovery_skip_until"] = (
            now + timedelta(minutes=args.quota_recovery_stable_minutes)
        ).isoformat()
        state["last_run_at"] = now.isoformat()
        state["last_quota_recovery_skip_at"] = now.isoformat()
        save_state(state)
        print(
            "YouTube queue monitor skipped; quota recovered but local queue is unchanged, "
            f"next full check in {args.quota_recovery_stable_minutes} min."
        )
        return []

    last_run = parse_dt(state.get("last_run_at"))
    if not args.force and last_run:
        next_allowed = last_run + timedelta(minutes=args.interval_minutes)
        if now < next_allowed:
            remaining = round((next_allowed - now).total_seconds() / 60.0, 1)
            print(f"YouTube queue monitor skipped; next run allowed in {remaining} min.")
            return []

    last_full_run = parse_dt(state.get("last_full_run_at"))
    if (
        not args.force
        and args.stable_skip_minutes > 0
        and last_full_run
        and state.get("last_queue_signature") == current_queue_signature
        and int(state.get("last_update_count") or 0) == 0
        and int(state.get("last_metadata_update_count") or 0) == 0
    ):
        next_full = last_full_run + timedelta(minutes=args.stable_skip_minutes)
        if now < next_full:
            remaining = round((next_full - now).total_seconds() / 60.0, 1)
            state["last_run_at"] = now.isoformat()
            state["last_stable_skip_at"] = now.isoformat()
            save_state(state)
            print(f"YouTube queue monitor skipped; queue unchanged and clean, next full check in {remaining} min.")
            return []

    try:
        youtube_performance_sync.main(
            ["--summary-only", "--max-age-minutes", str(args.performance_max_age_minutes)]
        )
    except Exception as exc:
        print(f"⚠️  YouTube performance sync failed; using cached summary if available: {exc}")
        if is_quota_error(exc):
            state["quota_blocked_until"] = (now + timedelta(hours=args.quota_backoff_hours)).isoformat()
            state["last_quota_error_at"] = now.isoformat()
            save_state(state)
            print(f"YouTube queue monitor: quota backoff set for {args.quota_backoff_hours} hour(s).")
            return []
    bot = YouTubeHomeRunBot()
    if not getattr(bot, "youtube", None):
        raise SystemExit("YouTube authentication is not available.")

    try:
        updates = bot.reschedule_pending_posts(
            dry_run=not args.apply,
            reorder=not args.no_reorder,
            min_lead_minutes=args.min_lead_minutes,
        )
    except Exception as exc:
        if is_quota_error(exc):
            state["quota_blocked_until"] = (now + timedelta(hours=args.quota_backoff_hours)).isoformat()
            state["last_quota_error_at"] = now.isoformat()
            save_state(state)
            print(f"YouTube queue monitor: quota backoff set for {args.quota_backoff_hours} hour(s).")
            return []
        raise
    metadata_updates = []
    if not args.no_metadata:
        try:
            metadata_updates = bot.optimize_scheduled_metadata(
                dry_run=not args.apply,
                min_lead_minutes=args.min_lead_minutes,
            )
        except Exception as exc:
            if is_quota_error(exc):
                state["quota_blocked_until"] = (now + timedelta(hours=args.quota_backoff_hours)).isoformat()
                state["last_quota_error_at"] = now.isoformat()
                save_state(state)
                print(f"YouTube queue monitor: quota backoff set for {args.quota_backoff_hours} hour(s).")
                return updates
            raise
    state.update(
        {
            "last_run_at": now.isoformat(),
            "last_apply": bool(args.apply),
            "last_update_count": len(updates),
            "last_metadata_update_count": len(metadata_updates),
            "interval_minutes": args.interval_minutes,
            "min_lead_minutes": args.min_lead_minutes,
            "quota_blocked_until": None,
            "quota_recovery_skip_until": None,
            "last_full_run_at": now.isoformat(),
            "last_queue_signature": current_queue_signature,
            "stable_skip_minutes": args.stable_skip_minutes,
            "performance_max_age_minutes": args.performance_max_age_minutes,
            "quota_recovery_stable_minutes": args.quota_recovery_stable_minutes,
        }
    )
    save_state(state)
    action = "Updated" if args.apply else "Would update"
    print(f"YouTube queue monitor: {action} {len(updates)} scheduled video(s).")
    if not args.no_metadata:
        print(f"YouTube queue monitor: {action} metadata on {len(metadata_updates)} scheduled video(s).")
    return updates


if __name__ == "__main__":
    main()
