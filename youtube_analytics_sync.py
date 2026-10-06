#!/usr/bin/env python3
"""
Backfill YouTube Analytics for uploaded HomerTrakker videos.

This pulls per-video metrics from the YouTube Analytics API, stores raw rows,
and writes a compact summary that the uploader can use as a ranking prior.

Requires YouTube Analytics access with the youtube.readonly scope.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = Path.home() / ".homer"
LEDGER_PATH = STATE_DIR / "uploads.json"
SUMMARY_PATH = STATE_DIR / "youtube_analytics_summary.json"
RAW_DIR = BASE_DIR / "logs" / "youtube_analytics"
TOKEN_FILE = BASE_DIR / "youtube_analytics_token.json"
CREDS_FILE = BASE_DIR / "config" / "youtube_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
EASTERN = ZoneInfo("America/New_York")


def load_ledger() -> dict:
    try:
        if LEDGER_PATH.exists():
            return json.loads(LEDGER_PATH.read_text())
    except Exception:
        pass
    return {}


def parse_batter(title: str) -> str:
    m = re.match(r"^(.*?)\s+(?:HR|Home Run)\b", title or "", re.I)
    batter = m.group(1).strip() if m else "Unknown Player"
    return re.sub(r"\s+\d+(?:\.\d+)?\s*(?:MPH|FT)\s*$", "", batter, flags=re.I).strip()


def parse_statcast_score(title: str) -> float:
    """Rough title-based score for later use in ranking."""
    score = 0.0
    m = re.search(r"Distance\s+(\d+)", title or "")
    if m:
        score += float(m.group(1))
    m = re.search(r"Exit Velocity\s+([\d.]+)", title or "")
    if m:
        score += float(m.group(1)) * 12.0
    m = re.search(r"Launch Angle\s+([\d.]+)", title or "")
    if m:
        la = float(m.group(1))
        score += max(0.0, 50.0 - abs(la - 28.0)) * 4.0
    return round(score, 3)


def authenticate():
    credentials = None
    noninteractive = not sys.stdout.isatty() or os.getenv("HOMER_NONINTERACTIVE") == "1"

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception:
                credentials = None

        if not credentials or not credentials.valid:
            if not CREDS_FILE.exists():
                raise SystemExit("YouTube credentials file not found.")
            if noninteractive:
                raise SystemExit(
                    "Analytics auth required. Run this script once in a browser-capable shell to refresh youtube_token.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            credentials = flow.run_local_server(
                port=0,
                open_browser=True,
                prompt="select_account",
                authorization_prompt_message="Please authorize access to read YouTube analytics.",
                success_message="Authentication complete. You can close this tab and return to the terminal.",
            )

        TOKEN_FILE.write_text(credentials.to_json())

    return credentials


def build_analytics_service(credentials):
    return build("youtubeAnalytics", "v2", credentials=credentials)


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def parse_date(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EASTERN)
    return dt


def fetch_metrics_for_date(service, video_ids, start_date, end_date):
    if not video_ids:
        return []

    rows = []
    for batch in chunked(video_ids, 200):
        resp = (
            service.reports()
            .query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,likes,averageViewDuration,estimatedMinutesWatched",
                dimensions="video",
                filters="video==" + ",".join(batch),
                sort="-views",
            )
            .execute()
        )
        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        for row in resp.get("rows", []) or []:
            item = dict(zip(headers, row))
            rows.append(item)
    return rows


def main():
    ledger = load_ledger()
    if not ledger:
        print("No upload ledger found.")
        return

    credentials = authenticate()
    service = build_analytics_service(credentials)

    by_upload_date = defaultdict(list)
    meta_by_video = {}
    for key, meta in ledger.items():
        video_id = meta.get("video_id")
        uploaded_at = meta.get("uploaded_at")
        if not video_id or not uploaded_at:
            continue
        try:
            upload_dt = parse_date(uploaded_at)
        except Exception:
            continue
        upload_date = upload_dt.astimezone(EASTERN).date().isoformat()
        by_upload_date[upload_date].append(video_id)
        meta_by_video[video_id] = meta

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    raw_rows = []
    for upload_date, video_ids in sorted(by_upload_date.items()):
        end_date = (datetime.fromisoformat(upload_date) + timedelta(days=1)).date().isoformat()
        rows = fetch_metrics_for_date(service, video_ids, upload_date, end_date)
        for row in rows:
            video_id = row.get("video")
            meta = meta_by_video.get(video_id, {})
            title = meta.get("title", "")
            row["title"] = title
            row["player"] = parse_batter(title)
            row["statcast_score"] = parse_statcast_score(title)
            row["upload_date"] = upload_date
            raw_rows.append(row)

    raw_path = RAW_DIR / f"youtube_analytics_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    raw_path.write_text(json.dumps(raw_rows, indent=2))

    player_bucket = defaultdict(list)
    for row in raw_rows:
        player_bucket[row["player"]].append(row)

    def avg(values, key):
        nums = [float(v.get(key, 0) or 0) for v in values]
        return sum(nums) / len(nums) if nums else 0.0

    summary = {
        "generated_at": datetime.now().isoformat(),
        "video_count": len(raw_rows),
        "by_player": {},
        "top_videos_by_views": sorted(
            [
                {
                    "video": r.get("video"),
                    "title": r.get("title"),
                    "views": float(r.get("views", 0) or 0),
                    "likes": float(r.get("likes", 0) or 0),
                    "averageViewDuration": float(r.get("averageViewDuration", 0) or 0),
                    "estimatedMinutesWatched": float(r.get("estimatedMinutesWatched", 0) or 0),
                }
                for r in raw_rows
            ],
            key=lambda x: x["views"],
            reverse=True,
        )[:25],
    }

    player_scores = []
    for player, rows in player_bucket.items():
        mean_views = avg(rows, "views")
        mean_likes = avg(rows, "likes")
        mean_watch = avg(rows, "estimatedMinutesWatched")
        mean_vd = avg(rows, "averageViewDuration")
        popularity_score = (
            math.log1p(mean_views) * 100.0
            + math.log1p(mean_likes + 1.0) * 20.0
            + math.log1p(mean_watch + 1.0) * 8.0
            + min(mean_vd, 180.0) * 0.5
        )
        player_scores.append((player, popularity_score, mean_views, len(rows)))

    if player_scores:
        raw_scores = [x[1] for x in player_scores]
        lo = min(raw_scores)
        hi = max(raw_scores)
        span = hi - lo if hi > lo else 1.0
        for player, score, mean_views, n in player_scores:
            norm_score = (score - lo) / span
            summary["by_player"][player] = {
                "uploads": n,
                "mean_views_1d": round(mean_views, 3),
                "popularity_score": round(score, 3),
                "popularity_rank_score": round(norm_score * 100.0, 3),
            }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {raw_path}")
    print(f"Wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
