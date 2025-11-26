"""更新 YT 搜索缓存的简化工具（支持测试用假搜索函数）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.core.normalize import make_key

from .client import get_client
from .search import search_song


def update_yt_cache(
    songs: Sequence[Dict[str, Any]],
    cache: SongCache,
    *,
    headers: Optional[Path] = None,
    yt_limit: int = 3,
    overrides: Optional[Dict[str, Any]] = None,
    search_fn=None,
    auth_mode: str = "headers",
    **_: Any,
) -> None:
    """
    为给定歌曲列表补充 YT 的 videoId/album_year 缓存。
    可传入 search_fn(yt_or_ctx, title, artists, limit) 便于测试。
    """
    overrides = overrides or {}
    yt = None
    if search_fn is None:
        yt = get_client(auth_mode, headers_path=headers if headers else None)
        search_fn = lambda yt_obj, t, a, limit: search_song(yt_obj, t, a, limit)  # noqa: E731

    for song in songs:
        title = song.get("title", "")
        artists = song.get("artists", "")
        key = make_key(title, artists)

        ov = overrides.get(key, {})
        if ov.get("videoId"):
            cache.set(key, "yt", "videoId", ov["videoId"])
        if ov.get("album_year"):
            cache.set(key, "yt", "album_year", ov["album_year"])

        if cache.get(key, "yt", "videoId"):
            continue

        try:
            found = search_fn(yt, title, artists, yt_limit)
        except Exception:
            found = None

        # 兼容测试中返回 list 的假搜索函数
        if isinstance(found, list) and found:
            found = found[0]

        if isinstance(found, dict) and found.get("videoId"):
            cache.set(key, "yt", "videoId", found["videoId"])
            album_year = found.get("album_year")
            if not album_year:
                album = found.get("album") or {}
                album_year = album.get("year") or album.get("releaseYear")
            if album_year:
                cache.set(key, "yt", "album_year", album_year)

    cache.save()


__all__ = ["update_yt_cache"]
