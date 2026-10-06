from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return [value] if value else []


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _item_text(item: Dict[str, Any]) -> str:
    media = item.get("media") or {}
    parts = [str(item.get(k) or "") for k in ("headline", "title", "blurb", "description")]
    parts.append(str(media.get("title") or ""))
    return _norm(" ".join(parts))


def _collect_content_items(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect playable MLB content items across the shapes used by the API."""
    items: List[Dict[str, Any]] = []
    highlights = content.get("highlights") or {}
    items.extend(_as_list((highlights.get("highlights") or {}).get("items")))
    items.extend(_as_list((highlights.get("live") or {}).get("items")))

    editorial = content.get("editorial") or {}
    recap = editorial.get("recap") or {}
    if isinstance(recap.get("mlb"), dict):
        items.append(recap["mlb"])
    items.extend(_as_list(recap.get("items")))
    items.extend(_as_list((editorial.get("featured") or {}).get("items")))
    items.extend(_as_list((editorial.get("highlights") or {}).get("items")))

    media = content.get("media") or {}
    for group in _as_list(media.get("epg")) + _as_list(media.get("epgAlternate")):
        if isinstance(group, dict):
            items.extend(_as_list(group.get("items")))

    deduped: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        urls = _playbacks(item)
        key = _clip_key(item, urls) or str(id(item))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _keyword_values(item: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield from _as_list(item.get("keywordsAll"))
    media = item.get("media") or {}
    yield from _as_list(media.get("keywordsAll"))


def _player_ids(item: Dict[str, Any]) -> Set[str]:
    ids: Set[str] = set()
    for kw in _keyword_values(item):
        if not isinstance(kw, dict):
            continue
        for key in ("playerId", "personId", "player_id", "person_id"):
            if kw.get(key) is not None:
                ids.add(str(kw[key]))
        value = str(kw.get("value") or "").lower()
        match = re.search(r"playerid-(\d+)", value)
        if match:
            ids.add(match.group(1))
        if kw.get("type") in {"player_id", "person_id"} and value.isdigit():
            ids.add(value)
    return ids


def _last_name(name: str) -> str:
    parts = _norm(name).split()
    return parts[-1] if parts else ""


def _item_has_batter(item: Dict[str, Any], batter_id: Optional[int], batter_name: str) -> bool:
    if batter_id is not None and str(batter_id) in _player_ids(item):
        return True
    text = _item_text(item)
    full = _norm(batter_name)
    last = _last_name(batter_name)
    return bool((full and full in text) or (last and last in text))


def _is_hr_item(item: Dict[str, Any]) -> bool:
    text = _item_text(item)
    if any(word in text for word in ("home run", "homers", "homer")):
        return True
    return any((kw.get("value") == "home-run" if isinstance(kw, dict) else False) for kw in _keyword_values(item))


def _playbacks(item: Dict[str, Any]) -> List[str]:
    media = item.get("media") or {}
    urls = []
    for pb in _as_list(item.get("playbacks")) + _as_list(media.get("playbacks")):
        if isinstance(pb, dict):
            url = pb.get("url") or ""
            if isinstance(url, str) and re.search(r"\.mp4(\?|$)", url, re.I) and url not in urls:
                urls.append(url)
    return urls


def _clip_key(item: Dict[str, Any], urls: List[str]) -> str:
    for key in ("guid", "id", "mediaPlaybackId"):
        if item.get(key):
            return str(item[key])
    return urls[0] if urls else ""


def _parse_date(item: Dict[str, Any]) -> datetime:
    raw = str(item.get("date") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _pick_4000k_or_first(urls: List[str]) -> Optional[str]:
    for url in urls:
        if re.search(r"4000k", url, re.I):
            return url
    return urls[0] if urls else None


def _ordered_entries(
    chosen: Tuple[Dict[str, Any], List[str], str],
    playable: List[Tuple[Dict[str, Any], List[str], str]],
    play: Dict[str, Any],
    order: int,
) -> List[Tuple[Dict[str, Any], List[str], str]]:
    rest = [entry for entry in playable if entry is not chosen]
    rest.sort(key=lambda entry: (-_score_item(entry[0], play, order), _parse_date(entry[0]), str(entry[0].get("id") or "")))
    return [chosen] + rest


def _batter_id(play: Dict[str, Any]) -> Optional[int]:
    return ((play.get("matchup") or {}).get("batter") or {}).get("id")


def _batter_name(play: Dict[str, Any]) -> str:
    return ((play.get("matchup") or {}).get("batter") or {}).get("fullName") or ""


def _player_homer_order(play: Dict[str, Any], all_hr_plays: List[Dict[str, Any]]) -> Tuple[int, int]:
    batter_id = _batter_id(play)
    at_bat = (play.get("about") or {}).get("atBatIndex")
    same_player = [
        p for p in all_hr_plays
        if _batter_id(p) == batter_id
    ]
    same_player.sort(key=lambda p: ((p.get("about") or {}).get("atBatIndex") or 0))
    for idx, candidate in enumerate(same_player, 1):
        if (candidate.get("about") or {}).get("atBatIndex") == at_bat:
            return idx, len(same_player)
    return 1, len(same_player) or 1


def _score_item(item: Dict[str, Any], play: Dict[str, Any], order: int) -> int:
    text = _item_text(item)
    about = play.get("about") or {}
    result = play.get("result") or {}
    score = 0
    inning = str(about.get("inning") or "")
    half = _norm(about.get("halfInning") or "")
    if inning and inning in text:
        score += 1
    if half and half in text:
        score += 1
    description_words = [w for w in _norm(result.get("description") or "").split() if len(w) > 3]
    score += min(4, sum(1 for word in set(description_words) if word in text))
    order_words = {
        1: ("first", "1st", "solo"),
        2: ("second", "2nd", "two"),
        3: ("third", "3rd", "three"),
    }.get(order, ())
    if any(word in text for word in order_words):
        score += 3
    return score


def select_homer_clip(
    content: Dict[str, Any],
    play: Dict[str, Any],
    all_hr_plays: List[Dict[str, Any]],
    used_clip_ids: Optional[Set[str]] = None,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    batter_id = _batter_id(play)
    batter_name = _batter_name(play)
    used_clip_ids = used_clip_ids or set()
    items = _collect_content_items(content)

    hr_candidates = [
        item for item in items
        if _is_hr_item(item) and _item_has_batter(item, batter_id, batter_name)
    ]
    candidates = hr_candidates or [
        item for item in items
        if _item_has_batter(item, batter_id, batter_name)
    ]

    playable = []
    for item in candidates:
        urls = _playbacks(item)
        if not urls:
            continue
        key = _clip_key(item, urls)
        if key and key in used_clip_ids:
            continue
        playable.append((item, urls, key))

    if not playable:
        return None, None, {
            "matchedBy": "noAvailableClip",
            "pickedFrom": "",
            "clipGuid": "",
            "atBatIndex": (play.get("about") or {}).get("atBatIndex"),
        }

    order, total = _player_homer_order(play, all_hr_plays)
    playable.sort(key=lambda entry: (_parse_date(entry[0]), str(entry[0].get("id") or "")))
    matched_by = "single"

    if total > 1:
        scored = sorted(
            ((entry, _score_item(entry[0], play, order)) for entry in playable),
            key=lambda entry: entry[1],
            reverse=True,
        )
        if len(scored) > 1 and scored[0][1] > scored[1][1] and scored[0][1] > 0:
            chosen = scored[0][0]
            item, urls, key = chosen
            matched_by = "textScore"
        elif len(playable) >= total and order <= len(playable):
            chosen = playable[order - 1]
            item, urls, key = chosen
            matched_by = "playerHrOrder"
        else:
            return None, None, {
                "matchedBy": "ambiguousMultiHr",
                "pickedFrom": "",
                "clipGuid": "",
                "atBatIndex": (play.get("about") or {}).get("atBatIndex"),
            }
    else:
        chosen = playable[0]
        item, urls, key = chosen

    ordered = _ordered_entries(chosen, playable, play, order)
    diamond = [url for _, entry_urls, _ in ordered for url in entry_urls if "mlb-cuts-diamond.mlb.com" in url]
    darkroom = [url for _, entry_urls, _ in ordered for url in entry_urls if "darkroom-clips.mlb.com" in url]
    produced = [url for _, entry_urls, _ in ordered for url in entry_urls if "bdata-producedclips.mlb.com" in url]
    broadcast = _pick_4000k_or_first(diamond)
    animated = darkroom[0] if darkroom else None
    if not broadcast and os.getenv("HOMER_ALLOW_PRODUCED") == "1":
        broadcast = produced[0] if produced else None

    if not (broadcast or animated):
        return None, None, {
            "matchedBy": "noSupportedPlayback",
            "pickedFrom": item.get("headline") or item.get("title") or "",
            "clipGuid": key,
            "atBatIndex": (play.get("about") or {}).get("atBatIndex"),
        }

    return broadcast, animated, {
        "matchedBy": matched_by,
        "pickedFrom": item.get("headline") or item.get("title") or "",
        "clipGuid": key,
        "atBatIndex": (play.get("about") or {}).get("atBatIndex"),
    }
