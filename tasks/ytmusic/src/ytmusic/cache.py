"""YT 相关的缓存填充工具。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.core.normalize import make_key
from tasks.ytmusic.src.logging.logger import get_logger

from .search import search_song


def ensure_yt_cache_for_song(
    song: Dict[str, Any],
    cache: SongCache,
    yt,
    *,
    yt_limit: int = 5,
    logger=None,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    search_fn=None,
) -> Dict[str, Any]:
    """
    为单首歌曲补齐 videoId/album_year 并写入缓存。
    返回 dict: {"videoId": ..., "album_year": ..., "status": ...}
    status: cache_hit/search_hit/search_miss/override/exists/error
    """
    logger = logger or get_logger(__name__)
    overrides = overrides or {}
    search_fn = search_fn or (lambda yt_obj, t, a, l: search_song(yt_obj, t, a, l))

    title = song.get("title", "")
    artists = song.get("artists", "")
    key = make_key(title, artists)

    # override 优先
    ov = overrides.get(key, {})
    if ov.get("videoId"):
        cache.set(key, "yt", "videoId", ov["videoId"])
        if ov.get("album_year"):
            cache.set(key, "yt", "album_year", ov["album_year"])
        return {"videoId": ov.get("videoId", ""), "album_year": ov.get("album_year", ""), "status": "override"}

    # 缓存命中
    cached_vid = cache.get(key, "yt", "videoId")
    if cached_vid:
        return {"videoId": cached_vid, "album_year": cache.get(key, "yt", "album_year") or "", "status": "cache_hit"}

    # 已有 videoId 输入直接写缓存
    if song.get("videoId"):
        cache.set(key, "yt", "videoId", song["videoId"])
        if song.get("album_year"):
            cache.set(key, "yt", "album_year", song["album_year"])
        logger.info(
            "行内已有 videoId title=%s artists=%s videoId=%s album_year=%s",
            title,
            artists,
            song["videoId"],
            song.get("album_year", ""),
        )
        return {"videoId": song["videoId"], "album_year": song.get("album_year", ""), "status": "exists"}

    # 搜索
    try:
        found = search_fn(yt, title, artists, yt_limit)
    except Exception as e:  # noqa: BLE001
        logger.error("搜索失败 title=%s artists=%s err=%s", title, artists, e)
        return {"videoId": "", "album_year": "", "status": "error"}

    if found and isinstance(found, list) and found:
        found = found[0]

    if isinstance(found, dict) and found.get("videoId"):
        vid = found["videoId"]
        album_year = found.get("album_year")
        if not album_year:
            album = found.get("album") or {}
            album_year = album.get("year") or album.get("releaseYear")
        cache.set(key, "yt", "videoId", vid)
        if album_year:
            cache.set(key, "yt", "album_year", album_year)
        logger.info("找到视频 title=%s artists=%s videoId=%s album_year=%s", title, artists, vid, album_year or "")
        return {"videoId": vid, "album_year": album_year or "", "status": "search_hit"}

    logger.warning("未找到视频 title=%s artists=%s (yt_limit=%s)", title, artists, yt_limit)
    return {"videoId": "", "album_year": "", "status": "search_miss"}


__all__ = ["ensure_yt_cache_for_song"]
