#!/usr/bin/env python3
"""
Sync current YouTube video performance using the YouTube Data API.

This intentionally uses the existing uploader token, so it works before the
separate YouTube Analytics OAuth flow is authorized. It writes the same summary
path consumed by youtube_homer_bot.py for queue ranking.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = Path.home() / ".homer"
LEDGER_PATH = STATE_DIR / "uploads.json"
QUEUE_PATH = STATE_DIR / "youtube_queue.json"
SUMMARY_PATH = STATE_DIR / "youtube_analytics_summary.json"
RAW_DIR = BASE_DIR / "logs" / "youtube_data_api"
LATEST_PATH = BASE_DIR / "logs" / "youtube_video_stats_latest.json"
TOKEN_FILE = BASE_DIR / "youtube_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
EASTERN = ZoneInfo("America/New_York")


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def cached_summary_is_fresh(max_age_minutes):
    if max_age_minutes <= 0 or not SUMMARY_PATH.exists():
        return None
    summary = load_json(SUMMARY_PATH, {})
    generated_at = parse_dt(summary.get("generated_at"))
    if not generated_at:
        return None
    age_minutes = (datetime.now(timezone.utc) - generated_at).total_seconds() / 60.0
    if age_minutes <= max_age_minutes:
        return summary
    return None


def parse_batter(title: str) -> str:
    m = re.match(r"^(.*?)\s+(?:HR|Home Run)\b", title or "", re.I)
    batter = m.group(1).strip() if m else "Unknown Player"
    return re.sub(r"\s+\d+(?:\.\d+)?\s*(?:MPH|FT)\s*$", "", batter, flags=re.I).strip()


def parse_stat(title: str, kind: str):
    patterns = {
        "distance": [r"Distance\s+(\d+)", r"(\d+)\s*ft"],
        "exit_velocity": [r"Exit Velocity\s+([\d.]+)", r"([\d.]+)\s*MPH"],
        "launch_angle": [r"Launch Angle\s+([\d.]+)", r"([\d.]+)\s*(?:deg|°)"],
    }
    for pattern in patterns[kind]:
        match = re.search(pattern, title or "", re.I)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                return None
    return None


def statcast_score(title: str) -> float:
    distance = parse_stat(title, "distance")
    ev = parse_stat(title, "exit_velocity")
    la = parse_stat(title, "launch_angle")
    score = 0.0
    if distance is not None:
        score += distance * 0.7
    if ev is not None:
        score += ev * 15.0
        if ev >= 110:
            score += 250.0
        elif ev >= 107:
            score += 120.0
        elif ev >= 105:
            score += 60.0
    if la is not None:
        score += max(0.0, 55.0 - abs(la - 23.0) * 5.0)
        if la > 34:
            score -= 80.0
    return round(score, 3)


def feature_bucket(row, feature: str):
    if feature == "exit_velocity":
        value = row.get("exit_velocity")
        if value is None:
            return None
        if value >= 110:
            return "110+"
        if value >= 107:
            return "107-109.9"
        if value >= 105:
            return "105-106.9"
        if value >= 100:
            return "100-104.9"
        return "<100"
    if feature == "launch_angle":
        value = row.get("launch_angle")
        if value is None:
            return None
        if value < 20:
            return "<20"
        if value <= 24:
            return "20-24"
        if value <= 29:
            return "25-29"
        if value <= 34:
            return "30-34"
        return "35+"
    if feature == "distance":
        value = row.get("distance")
        if value is None:
            return None
        if value >= 420:
            return "420+"
        if value >= 400:
            return "400-419"
        if value >= 380:
            return "380-399"
        return "<380"
    if feature == "publish_hour_et":
        value = row.get("publish_hour_et")
        return str(value) if value is not None else None
    return None


def summarize_feature_lifts(rows, baseline_median):
    baseline = max(float(baseline_median or 0), 1.0)
    output = {}
    for feature in ["exit_velocity", "launch_angle", "distance", "publish_hour_et"]:
        grouped = defaultdict(list)
        for row in rows:
            bucket = feature_bucket(row, feature)
            if bucket is not None:
                grouped[bucket].append(row)
        output[feature] = {}
        for bucket, values in grouped.items():
            view_values = [row.get("views", 0) for row in values]
            bucket_median = median(view_values) if view_values else 0
            shrink = len(values) / (len(values) + 5.0)
            lift_score = math.log((bucket_median + 50.0) / (baseline + 50.0)) * 120.0 * shrink
            output[feature][bucket] = {
                "count": len(values),
                "median_views": bucket_median,
                "mean_views": round(sum(view_values) / len(view_values), 3) if view_values else 0,
                "lift_vs_baseline": round((bucket_median - baseline) / baseline, 3),
                "rank_score": round(max(-120.0, min(120.0, lift_score)), 3),
            }
    return output


def authenticate():
    if not TOKEN_FILE.exists():
        raise SystemExit("youtube_token.json not found; run YouTube uploader auth first.")
    credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_FILE.write_text(credentials.to_json())
    return build("youtube", "v3", credentials=credentials)


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def fetch_rows():
    ledger = load_json(LEDGER_PATH, {})
    queue = load_json(QUEUE_PATH, {"items": {}})
    queue_by_video = {
        item.get("video_id"): item
        for item in (queue.get("items") or {}).values()
        if item.get("video_id")
    }

    ids = []
    meta_by_video = {}
    for key, meta in ledger.items():
        video_id = meta.get("video_id")
        if not video_id:
            continue
        ids.append(video_id)
        meta_by_video[video_id] = {"key": key, **meta}

    youtube = authenticate()
    rows = []
    missing = set(ids)
    for batch in chunked(ids, 50):
        resp = (
            youtube.videos()
            .list(part="snippet,status,statistics,contentDetails", id=",".join(batch))
            .execute()
        )
        for item in resp.get("items", []):
            video_id = item.get("id")
            missing.discard(video_id)
            stats = item.get("statistics") or {}
            status = item.get("status") or {}
            snippet = item.get("snippet") or {}
            meta = meta_by_video.get(video_id) or {}
            queue_item = queue_by_video.get(video_id) or {}
            title = meta.get("title") or snippet.get("title") or ""

            def as_int(name):
                try:
                    return int(stats.get(name, 0) or 0)
                except Exception:
                    return 0

            publish_at = (
                queue_item.get("publish_at")
                or status.get("publishAt")
                or snippet.get("publishedAt")
                or meta.get("uploaded_at")
            )
            row = {
                "video_id": video_id,
                "key": meta.get("key"),
                "title": title,
                "player": parse_batter(title),
                "uploaded_at": meta.get("uploaded_at"),
                "snippet_published_at": snippet.get("publishedAt"),
                "queue_publish_at": queue_item.get("publish_at"),
                "publish_at": publish_at,
                "privacy_status": status.get("privacyStatus"),
                "status_publish_at": status.get("publishAt"),
                "upload_status": status.get("uploadStatus"),
                "views": as_int("viewCount"),
                "likes": as_int("likeCount"),
                "comments": as_int("commentCount"),
                "duration": (item.get("contentDetails") or {}).get("duration"),
                "distance": parse_stat(title, "distance"),
                "exit_velocity": parse_stat(title, "exit_velocity"),
                "launch_angle": parse_stat(title, "launch_angle"),
                "statcast_score": statcast_score(title),
            }
            rows.append(row)

    return rows, sorted(missing)


def build_summary(rows, generated_at):
    now = parse_dt(generated_at) or datetime.now(timezone.utc)
    for row in rows:
        publish_dt = parse_dt(row.get("publish_at"))
        row["age_hours"] = round((now - publish_dt).total_seconds() / 3600.0, 3) if publish_dt else None
        row["publish_day_et"] = publish_dt.astimezone(EASTERN).date().isoformat() if publish_dt else None
        row["publish_hour_et"] = publish_dt.astimezone(EASTERN).hour if publish_dt else None
        row["evaluable"] = row.get("privacy_status") == "public" and (row.get("age_hours") or 0) >= 1.0
        row["mature"] = row.get("privacy_status") == "public" and (row.get("age_hours") or 0) >= 6.0
        row["suppression_candidate"] = bool(row.get("mature") and row.get("views", 0) < 50)

    evaluable = [row for row in rows if row["evaluable"]]
    by_day = defaultdict(list)
    for row in evaluable:
        if row.get("publish_day_et"):
            by_day[row["publish_day_et"]].append(row)
    day_stats = {}
    suspect_days = set()
    for day, values in by_day.items():
        view_values = [row.get("views", 0) for row in values]
        low_count = sum(1 for value in view_values if value < 50)
        zero_count = sum(1 for value in view_values if value == 0)
        low_rate = low_count / len(values) if values else 0.0
        day_median = median(view_values) if view_values else 0
        suspect = len(values) >= 8 and (day_median < 100 or low_rate >= 0.35)
        if suspect:
            suspect_days.add(day)
        day_stats[day] = {
            "count": len(values),
            "median_views": day_median,
            "mean_views": round(sum(view_values) / len(view_values), 3) if view_values else 0,
            "under_50_count": low_count,
            "zero_count": zero_count,
            "under_50_rate": round(low_rate, 3),
            "suspect_spam_day": suspect,
        }
    for row in rows:
        row["suspect_spam_day"] = row.get("publish_day_et") in suspect_days
        row["trusted_for_learning"] = bool(
            row.get("evaluable")
            and row.get("views", 0) >= 50
            and not (row.get("suspect_spam_day") and row.get("views", 0) < 250)
        )

    trusted_learning = [row for row in rows if row.get("trusted_for_learning")]
    mature_clean = [row for row in rows if row["mature"] and row.get("trusted_for_learning")]
    player_rows = defaultdict(list)
    for row in mature_clean or trusted_learning or evaluable:
        if row.get("player") and row["player"] != "Unknown Player":
            player_rows[row["player"]].append(row)

    player_scores = []
    for player, values in player_rows.items():
        mean_views = sum(v.get("views", 0) for v in values) / len(values)
        mean_likes = sum(v.get("likes", 0) for v in values) / len(values)
        score = math.log1p(mean_views) * 100.0 + math.log1p(mean_likes + 1) * 25.0
        player_scores.append((player, score, mean_views, mean_likes, len(values)))

    rank_by_player = {}
    if player_scores:
        raw_scores = [score for _, score, _, _, _ in player_scores]
        lo = min(raw_scores)
        hi = max(raw_scores)
        span = hi - lo if hi > lo else 1.0
        for player, score, mean_views, mean_likes, n in player_scores:
            rank_by_player[player] = {
                "uploads": n,
                "mean_views": round(mean_views, 3),
                "mean_likes": round(mean_likes, 3),
                "popularity_score": round(score, 3),
                "popularity_rank_score": round(((score - lo) / span) * 100.0, 3),
            }

    recent_eligible = [
        row
        for row in rows
        if row.get("privacy_status") == "public" and (row.get("age_hours") or 0) >= 2.0
    ]
    recent_eligible.sort(key=lambda row: row.get("publish_at") or "")
    recent_tail = recent_eligible[-4:]
    guard_low_threshold = 50
    guard_limit = 2
    recent_bad = [row for row in recent_tail[-guard_limit:] if row.get("views", 0) < guard_low_threshold]
    guard_triggered = len(recent_tail) >= guard_limit and len(recent_bad) >= guard_limit

    eval_views = [row.get("views", 0) for row in evaluable]
    trusted_views = [row.get("views", 0) for row in trusted_learning]
    trusted_baseline = median(trusted_views) if trusted_views else (median(eval_views) if eval_views else 0)
    summary = {
        "generated_at": generated_at,
        "source": "youtube_data_api",
        "video_count": len(rows),
        "public_count": sum(1 for row in rows if row.get("privacy_status") == "public"),
        "private_count": sum(1 for row in rows if row.get("privacy_status") == "private"),
        "evaluable_count": len(evaluable),
        "trusted_learning_count": len(trusted_learning),
        "suppression_candidate_count": sum(1 for row in rows if row.get("suppression_candidate")),
        "baseline": {
            "median_views": median(eval_views) if eval_views else 0,
            "mean_views": round(sum(eval_views) / len(eval_views), 3) if eval_views else 0,
            "trusted_median_views": trusted_baseline,
            "trusted_mean_views": round(sum(trusted_views) / len(trusted_views), 3) if trusted_views else 0,
        },
        "by_publish_day": dict(sorted(day_stats.items())),
        "feature_lifts": summarize_feature_lifts(trusted_learning, trusted_baseline),
        "suppression_guard": {
            "triggered": guard_triggered,
            "low_view_threshold": guard_low_threshold,
            "consecutive_limit": guard_limit,
            "recommended_gap_minutes": 90 if guard_triggered else 30,
            "recommended_max_publishes_per_day": 4 if guard_triggered else 0,
            "recent_checked": [
                {
                    "video_id": row.get("video_id"),
                    "player": row.get("player"),
                    "views": row.get("views", 0),
                    "age_hours": row.get("age_hours"),
                    "publish_at": row.get("publish_at"),
                }
                for row in recent_tail
            ],
        },
        "by_player": rank_by_player,
        "top_videos_by_views": sorted(
            [
                {
                    "video": row.get("video_id"),
                    "title": row.get("title"),
                    "player": row.get("player"),
                    "views": row.get("views", 0),
                    "likes": row.get("likes", 0),
                    "publish_at": row.get("publish_at"),
                }
                for row in evaluable
            ],
            key=lambda row: row["views"],
            reverse=True,
        )[:25],
    }
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-only", action="store_true", help="Only print compact summary output.")
    parser.add_argument(
        "--max-age-minutes",
        type=float,
        default=0,
        help="Use cached summary when it is newer than this many minutes.",
    )
    args = parser.parse_args(argv)

    cached_summary = cached_summary_is_fresh(args.max_age_minutes)
    if cached_summary:
        guard = cached_summary["suppression_guard"]
        print(
            "YouTube performance sync: "
            f"{cached_summary['video_count']} videos, "
            f"{cached_summary['public_count']} public, "
            f"median {cached_summary['baseline']['median_views']} views, "
            f"guard_triggered={guard['triggered']} "
            "(cached)"
        )
        return cached_summary

    generated_at = datetime.now(timezone.utc).isoformat()
    rows, missing = fetch_rows()
    summary = build_summary(rows, generated_at)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"youtube_data_api_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    payload = {
        "generated_at": generated_at,
        "row_count": len(rows),
        "missing_video_ids": missing,
        "rows": rows,
    }
    raw_path.write_text(json.dumps(payload, indent=2))
    LATEST_PATH.write_text(json.dumps(payload, indent=2))
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    guard = summary["suppression_guard"]
    print(
        "YouTube performance sync: "
        f"{summary['video_count']} videos, "
        f"{summary['public_count']} public, "
        f"median {summary['baseline']['median_views']} views, "
        f"guard_triggered={guard['triggered']}"
    )
    if not args.summary_only:
        print(f"Wrote {raw_path}")
        print(f"Wrote {LATEST_PATH}")
        print(f"Wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
