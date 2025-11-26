from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .cache_utils import SongCache
from .normalize import make_key


def search_yt(yt: YTMusic, title: str, artists: str, limit: int) -> List[Dict[str, Any]]:
    query = f"{title} {artists}".strip()
    return yt.search(query, filter="songs", limit=limit)


def extract_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """从 ytmusic search 结果提取 videoId 和年份信息。"""
    video_id = result.get("videoId") or ""
    album = result.get("album") or {}
    album_year = None
    album_id = None
    if isinstance(album, dict):
        album_year = album.get("year") or album.get("releaseYear")
        album_id = album.get("id")
    # 部分结果有顶层 year 字段
    top_year = result.get("year")
    year = album_year or top_year or ""
    return {"videoId": video_id, "album_year": year, "album_id": album_id or "", "time_public": ""}


def update_yt_cache(
    songs: Sequence[Dict[str, Any]],
    cache: SongCache,
    *,
    headers: Path,
    overrides: Optional[Dict[str, Any]] = None,
    yt_limit: int = 3,
    max_lookups: int = 200,
    retry_delay: float = 1.0,
    retries: int = 1,
    refresh_existing: bool = False,
    refresh_year_only: bool = False,
    log_path: Optional[Path] = None,
    search_fn: Optional[Callable[[YTMusic, str, str, int], List[Dict[str, Any]]]] = None,
    fetch_album_year: bool = True,
    debug_song_dump: Optional[Path] = None,
    force_album_fetch: bool = False,
    song_meta_dump: Optional[Path] = None,
) -> None:
    """
    批量搜索 YT Music 获取 videoId 和年份信息，并写入缓存 yt.*。
    不修改 CSV，仅更新缓存和日志。
    """
    overrides = overrides or {}
    yt = None
    search = search_fn
    if search is None:
        try:
            from ytmusicapi import YTMusic  # type: ignore
        except Exception as exc:
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(json.dumps({"error": f"ytmusic_import_fail:{exc}"}, ensure_ascii=False))
            return
        yt = YTMusic(str(headers))
        search = search_yt
    else:
        yt = None  # 自定义 search 时不构造 YTMusic

    entries: List[str] = []
    lookups = 0
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    if debug_song_dump:
        debug_song_dump.parent.mkdir(parents=True, exist_ok=True)

    for idx, song in enumerate(songs):
        title = song.get("title", "")
        artists = song.get("artists", "")
        key = make_key(title, artists)

        override_vid = overrides.get(key, {}).get("videoId")
        cached_vid = cache.get(key, "yt", "videoId") or ""

        vid = "" if refresh_existing else cached_vid
        album_year = cache.get(key, "yt", "album_year") or ""
        reasons: List[str] = []

        if override_vid:
            vid = override_vid
            reasons.append("override_videoId")

        need_lookup = (
            (not vid)
            or refresh_existing
            or refresh_year_only
            or (fetch_album_year and not album_year)
        ) and (lookups < max_lookups)
        if need_lookup:
            attempt = 0
            results: List[Dict[str, Any]] = []
            while attempt <= retries:
                try:
                    results = search(yt, title, artists, yt_limit)
                    break
                except Exception as exc:
                    reasons.append(f"search_fail:{exc}")
                    if attempt >= retries:
                        break
                    time.sleep(retry_delay)
                    attempt += 1
            if results:
                fields = extract_fields(results[0])
                if not vid or refresh_existing:
                    vid = fields.get("videoId", "") or vid
                if not album_year or refresh_existing or refresh_year_only:
                    album_year = fields.get("album_year", "") or album_year
                album_id = fields.get("album_id") or ""
                reasons.append("yt_hit")
                cache.set(key, "yt", "search_top1", results[0])
                # 尝试查专辑信息获取年份
                if fetch_album_year and album_id and yt and (force_album_fetch or refresh_year_only or not album_year):
                    try:
                        album_meta = yt.get_album(album_id)
                        cache.set(key, "yt", "album_meta", album_meta)
                        year = album_meta.get("year") or album_meta.get("releaseYear")
                        if not year:
                            year = album_meta.get("release_date") or album_meta.get("releaseDate")
                        if year:
                            # 可能是 int 或 yyyy-mm-dd
                            album_year = str(year).split("-")[0]
                            reasons.append("album_year_from_album")
                        else:
                            reasons.append("album_year_missing_in_album")
                    except Exception as exc:
                        reasons.append(f"album_year_fetch_fail:{exc}")
                # 继续尝试用 get_song 获取 uploadDate
                if fetch_album_year and (not album_year or refresh_year_only) and (vid or fields.get("videoId")) and yt:
                    try:
                        vid_for_song = vid or fields.get("videoId")
                        song_meta = yt.get_song(vid_for_song)
                        cache.set(key, "yt", "song_meta", song_meta)
                        if debug_song_dump:
                            try:
                                existing = debug_song_dump.read_text() if debug_song_dump.exists() else ""
                                debug_song_dump.write_text(existing + json.dumps({"key": key, "song_meta": song_meta}, ensure_ascii=False, indent=2) + "\n")
                            except Exception:
                                pass
                        if song_meta_dump:
                            try:
                                song_meta_dump.write_text(json.dumps(song_meta, ensure_ascii=False, indent=2))
                            except Exception:
                                pass
                        mf = song_meta.get("microformat", {}).get("microformatDataRenderer", {}) if song_meta else {}
                        upload_date = mf.get("uploadDate") or mf.get("publishDate")
                        vd = song_meta.get("videoDetails", {}) if song_meta else {}
                        vd_date = vd.get("releaseDate") or vd.get("publishDate")
                        date_val = upload_date or vd_date
                        if date_val:
                            album_year = str(date_val).split("T")[0].split("-")[0]
                            reasons.append("album_year_from_song")
                        else:
                            reasons.append("album_year_missing_in_song")
                    except Exception as exc:
                        reasons.append(f"album_year_song_fetch_fail:{exc}")
            else:
                reasons.append("yt_miss")
            lookups += 1

        if vid:
            cache.set(key, "yt", "videoId", vid)
        if album_year:
            cache.set(key, "yt", "album_year", album_year)

        if log_path:
            entries.append(
                json.dumps(
                    {
                        "index": idx,
                        "key": key,
                        "title": title,
                        "artists": artists,
                        "videoId": vid,
                        "album_year": album_year,
                        "reasons": reasons,
                    },
                    ensure_ascii=False,
                )
            )

    cache.save()
    if log_path:
        content = "\n".join(entries) + "\n"
        log_path.write_text(content)


__all__ = ["update_yt_cache"]
