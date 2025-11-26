from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cache_utils import SongCache
from .normalize import make_key


def parse_year(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val).split("-")[0])
    except Exception:
        return None


def sort_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(r: Dict[str, Any]) -> tuple:
        if r.get("release_date"):
            return (0, r["release_date"], r.get("title", ""))
        y = parse_year(r.get("album_year", "") or r.get("time_public", ""))
        if y is not None:
            return (1, f"{y:04d}-12-31", r.get("title", ""))
        return (2, "9999-12-31", r.get("title", ""))

    return sorted(rows, key=key)


def search_yt(yt: YTMusic, title: str, artists: str, limit: int) -> Optional[str]:
    query = f"{title} {artists}".strip()
    try:
        results = yt.search(query, filter="songs", limit=limit)
    except Exception:
        return None
    for res in results:
        vid = res.get("videoId")
        if vid:
            return vid
    return None


def update_playlist(yt: YTMusic, playlist_id: str, video_ids: List[str]) -> None:
    pl = yt.get_playlist(playlist_id, limit=6000)
    items = [
        {"setVideoId": t.get("setVideoId"), "videoId": t.get("videoId")}
        for t in pl.get("tracks", [])
        if t.get("setVideoId") and t.get("videoId")
    ]
    for i in range(0, len(items), 50):
        yt.remove_playlist_items(playlist_id, items[i : i + 50])
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        try:
            yt.add_playlist_items(playlist_id, batch, duplicates=True)
        except YTMusicServerError:
            for v in batch:
                try:
                    yt.add_playlist_items(playlist_id, [v], duplicates=True)
                except YTMusicServerError:
                    continue


def apply_csv_to_playlist(
    headers: Path,
    csv_path: Path,
    playlist_id: str,
    *,
    cache_path: Path,
    yt_limit: int = 4,
    search_missing: bool = False,
    log_path: Optional[Path] = None,
) -> None:
    # 延迟导入，便于在无 ytmusicapi 的测试环境下复用排序等函数
    from ytmusicapi import YTMusic

    yt = YTMusic(headers)
    cache = SongCache(cache_path)

    rows = list(csv.DictReader(csv_path.open()))
    enriched: List[Dict[str, Any]] = []
    log_entries: List[Dict[str, Any]] = []

    for r in rows:
        title = r.get("title", "")
        artists = r.get("artists", "")
        video_id = r.get("videoId", "")
        key = make_key(title, artists)
        if not video_id and search_missing:
            cached_vid = cache.get(key, "yt", "videoId")
            if cached_vid:
                video_id = cached_vid
            else:
                vid = search_yt(yt, title, artists, yt_limit)
                if vid:
                    video_id = vid
                    cache.set(key, "yt", "videoId", vid)
        enriched.append({**r, "videoId": video_id})
        log_entries.append({**r, "videoId": video_id})

    sorted_rows = sort_rows(enriched)
    video_ids = [r.get("videoId") for r in sorted_rows if r.get("videoId")]
    update_playlist(yt, playlist_id, video_ids)

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as f:
            for e in log_entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.write(json.dumps({"summary": {"total": len(sorted_rows), "with_videoId": len(video_ids)}}, ensure_ascii=False) + "\n")

    cache.save()


__all__ = ["apply_csv_to_playlist", "sort_rows"]
