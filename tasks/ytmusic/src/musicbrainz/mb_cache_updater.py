from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.core.normalize import make_key, normalized_query

MB_USER_AGENT = "ytmusic-playlist-tool/1.0 (contact: none)"


def mb_search(title: str, artists: str, limit: int, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """调用 MusicBrainz 录音搜索。"""
    params = {
        "query": f'recording:"{title}" AND artist:"{artists}"',
        "fmt": "json",
        "limit": str(limit),
    }
    url = "https://musicbrainz.org/ws/2/recording/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": MB_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("recordings", [])


def best_mb_date(results: List[Dict[str, Any]]) -> Optional[str]:
    """从 MB 搜索结果中挑选最早日期。"""
    dates: List[str] = []
    for r in results:
        if r.get("first-release-date"):
            dates.append(r["first-release-date"])
        for rel in r.get("releases", []) or []:
            if rel.get("date"):
                dates.append(rel["date"])

    def normalize(d: str) -> str:
        parts = d.split("-")
        if len(parts) == 1:
            return f"{parts[0]}-12-31"
        if len(parts) == 2:
            return f"{parts[0]}-{parts[1]}-28"
        return d

    norm_dates = []
    for d in dates:
        try:
            norm_dates.append(normalize(d))
        except Exception:
            continue
    if not norm_dates:
        return None
    return min(norm_dates)


def parse_year(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val).split("-")[0])
    except Exception:
        return None


def is_suspicious(mb_date: str, fallback: Optional[str]) -> bool:
    """判定日期是否可疑：未来年份或与 fallback 相差过大。"""
    mb_year = parse_year(mb_date)
    if not mb_year:
        return False
    current_year = date.today().year
    if mb_year > current_year:
        return True
    if fallback:
        fb_year = parse_year(fallback)
        if fb_year and fb_year <= current_year and (mb_year - fb_year) > 2:
            return True
    return False


def fallback_date(row: Dict[str, Any]) -> Optional[str]:
    for field in ("album_year", "time_public"):
        val = row.get(field)
        y = parse_year(val) if val else None
        if y:
            return f"{y:04d}-12-31"
    return None


def update_mb_cache(
    songs: Sequence[Dict[str, Any]],
    cache: SongCache,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    mb_limit: int = 5,
    max_lookups: int = 200,
    retry_delay: float = 1.0,
    retries: int = 2,
    refresh_existing: bool = False,
    refresh_suspect: bool = False,
    log_path: Optional[Path] = None,
    search_fn: Callable[[str, str, int], List[Dict[str, Any]]] = mb_search,
) -> None:
    """
    查询 MusicBrainz 并写入缓存，不输出 CSV。
    缓存字段：
      mb.release_date 选定日期
      mb.suspect_release_date 可疑日期
      mb.raw/raw_query 原始请求与响应
    """
    overrides = overrides or {}
    entries: List[str] = []
    lookups = 0
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    for idx, song in enumerate(songs):
        title = song.get("title", "")
        artists = song.get("artists", "")
        key = make_key(title, artists)

        override_date = overrides.get(key, {}).get("release_date")
        fallback = fallback_date(song)
        cached_date = cache.get(key, "mb", "release_date") or ""
        cached_suspect = cache.get(key, "mb", "suspect_release_date") or ""

        release_date = "" if refresh_existing else cached_date
        source = "cache" if cached_date and not refresh_existing else ""
        reasons: List[str] = []

        if override_date:
            release_date = override_date
            source = "override"
            reasons.append("override")

        if cached_date and is_suspicious(cached_date, fallback):
            cache.set(key, "mb", "suspect_release_date", cached_date)
            release_date = ""
            source = ""
            reasons.append("cached_suspect")
            if not refresh_suspect:
                reasons.append("skip_suspect_cache")

        need_lookup = (not release_date and lookups < max_lookups) and (
            refresh_existing or not cached_date or (cached_suspect and refresh_suspect) or "cached_suspect" in reasons
        )

        if need_lookup:
            q_title, q_artist = normalized_query(title, artists)
            attempt = 0
            results: List[Dict[str, Any]] = []
            while attempt <= retries:
                try:
                    results = search_fn(q_title, q_artist, mb_limit)
                    break
                except Exception:
                    if attempt >= retries:
                        break
                    time.sleep(retry_delay)
                    attempt += 1
            mb_date = best_mb_date(results) or ""
            cache.set(key, "mb", "raw", results)
            cache.set(key, "mb", "raw_query", {"title": q_title, "artist": q_artist})
            lookups += 1
            if mb_date:
                if is_suspicious(mb_date, fallback):
                    cache.set(key, "mb", "suspect_release_date", mb_date)
                    reasons.append("mb_suspect")
                else:
                    release_date = mb_date
                    source = "mb"
                    cache.set(key, "mb", "release_date", mb_date)
                    reasons.append("mb_ok")
            else:
                cache.set(key, "mb", "release_date", "")
                reasons.append("mb_miss")

        if not release_date and fallback:
            release_date = fallback
            source = "fallback"
            reasons.append("fallback")

        if log_path:
            entry = {
                "index": idx,
                "key": key,
                "title": title,
                "artists": artists,
                "release_date": release_date,
                "source": source or ("suspect_cache" if cached_suspect and not refresh_suspect else "missing"),
                "fallback": fallback or "",
                "suspect_mb_date": cache.get(key, "mb", "suspect_release_date") or "",
                "reasons": reasons,
            }
            entries.append(json.dumps(entry, ensure_ascii=False))

    cache.save()
    if log_path and entries:
        log_path.write_text("\n".join(entries) + "\n")


__all__ = ["update_mb_cache", "mb_search", "best_mb_date", "is_suspicious"]
