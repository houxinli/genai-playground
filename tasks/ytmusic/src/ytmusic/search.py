"""封装 YT 搜索，返回精简的歌曲信息。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ytmusicapi import YTMusic


def _extract_result(result: Dict[str, Any]) -> Dict[str, Any]:
    video_id = result.get("videoId") or ""
    album = result.get("album") or {}
    album_year = None
    album_id = None
    if isinstance(album, dict):
        album_year = album.get("year") or album.get("releaseYear")
        album_id = album.get("id")
    top_year = result.get("year")
    year = album_year or top_year or ""
    return {
        "videoId": video_id,
        "album_year": year,
        "album_id": album_id or "",
        "time_public": "",
    }


def search_song(yt: YTMusic, title: str, artists: str, limit: int = 3) -> Optional[Dict[str, Any]]:
    """搜索歌曲，返回首个匹配的 videoId 和年份信息。"""
    query = f"{title} {artists}".strip()
    results: List[Dict[str, Any]] = yt.search(query, filter="songs", limit=limit) or []
    for res in results:
        if res.get("videoId"):
            return _extract_result(res)
    return None


__all__ = ["search_song"]
