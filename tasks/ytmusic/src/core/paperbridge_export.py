"""把本地歌单 CSV + 候选版本导出成 paperbridge `/music/` 的快照(schema v1)。

快照只描述"期望状态 + 可选版本";用户在网页上做的选择由
`paperbridge_api.music.cli choices` 取回,再按 ytmusic-sync 流程写回 CSV 并推送。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .normalize import make_key

# 网页上歌单的固定 id 与显示顺序;未列出的按 playlists.json 顺序排在后面。
PLAYLIST_SLUGS = {
    "昨日重现": "zuori",
    "not yet": "not-yet",
    "Yesterday once more": "yom",
    "中国风": "zhongguofeng",
    "日本語": "nihongo",
    "其它老歌": "qita",
}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def playlist_slug(title: str) -> str:
    if title in PLAYLIST_SLUGS:
        return PLAYLIST_SLUGS[title]
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return ascii_slug or "pl-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]


def _track(row: Dict[str, str], extra: Dict[str, Any]) -> Dict[str, Any]:
    video_id = (row.get("videoId") or "").strip()
    track: Dict[str, Any] = {
        "key": make_key(row.get("title", ""), row.get("artists", "")),
        "title": (row.get("title") or "").strip(),
        "artists": (row.get("artists") or "").strip(),
        "release_date": (row.get("release_date") or "").strip()[:10],
        "video_id": video_id if VIDEO_ID.match(video_id) else None,
    }
    current = extra.get("current")
    if current and track["video_id"]:
        track["current"] = {**current, "video_id": track["video_id"]}
    for field in ("ref_length_s", "note"):
        if extra.get(field):
            track[field] = extra[field]
    track["candidates"] = [c for c in extra.get("candidates", []) if c.get("video_id") != track["video_id"]]
    return track


def build_library(playlists_json: Path, candidates_json: Path | None, repo_root: Path) -> Dict[str, Any]:
    entries = [p for p in json.loads(playlists_json.read_text(encoding="utf-8")) if str(p.get("path", "")).endswith(".csv")]
    candidates = json.loads(candidates_json.read_text(encoding="utf-8")) if candidates_json and candidates_json.exists() else {}
    order = list(PLAYLIST_SLUGS)
    entries.sort(key=lambda p: order.index(p["title"]) if p["title"] in order else len(order))

    playlists: List[Dict[str, Any]] = []
    for entry in entries:
        rows = list(csv.DictReader((repo_root / entry["path"]).open(encoding="utf-8")))
        extras = candidates.get(entry["title"], {})
        tracks: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if not (row.get("title") or "").strip():
                continue
            track = _track(row, extras.get(make_key(row.get("title", ""), row.get("artists", "")), {}))
            tracks.setdefault(track["key"], track)  # CSV 内重复行只保留第一条
        playlists.append({
            "id": playlist_slug(entry["title"]),
            "name": entry["title"],
            "yt_playlist_id": entry.get("id"),
            "tracks": list(tracks.values()),
        })
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "playlists": playlists,
    }


__all__ = ["build_library", "playlist_slug"]
