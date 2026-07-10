from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.core.normalize import make_key


def parse_year(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val).split("-")[0])
    except Exception:
        return None


def choose_date(row: Dict[str, Any], cache: SongCache, overrides: Dict[str, Any]) -> Dict[str, Any]:
    key = make_key(row.get("title", ""), row.get("artists", ""))
    override_date = overrides.get(key, {}).get("release_date")
    mb_date = cache.get(key, "mb", "release_date") or ""
    mb_suspect = cache.get(key, "mb", "suspect_release_date") or ""
    yt_year = cache.get(key, "yt", "album_year") or ""
    qq_time = cache.get(key, "qq", "time_public") or row.get("time_public", "")
    yt_video = overrides.get(key, {}).get("videoId") or cache.get(key, "yt", "videoId") or row.get("videoId", "")
    album_year = row.get("album_year", "")
    time_public = row.get("time_public", "")
    fallback_year = None
    for src in (album_year, time_public):
        y = parse_year(src) if src else None
        if y:
            fallback_year = f"{y:04d}-12-31"
            break

    reasons: List[str] = []
    date_source = ""
    release_date = ""

    if override_date:
        # 人工 override 无条件生效，不参与"取最早"比较
        release_date = override_date
        date_source = "override"
        reasons.append("override")
    else:
        candidates = []
        if mb_date:
            candidates.append(("mb", mb_date))
        if qq_time:
            y = parse_year(qq_time)
            if y:
                candidates.append(("qq_time_public", qq_time if "-" in qq_time else f"{y:04d}-12-31"))
        if yt_year:
            y = parse_year(yt_year)
            if y:
                candidates.append(("yt_album_year", f"{y:04d}-12-31"))
        if fallback_year:
            candidates.append(("fallback", fallback_year))

        if candidates:
            # 选择最早日期
            source, date_val = sorted(candidates, key=lambda x: x[1])[0]
            release_date = date_val
            date_source = source
            reasons.append(source)
        else:
            release_date = ""
            date_source = "missing"
            reasons.append("missing")

    if mb_suspect and not override_date:
        # 标记可疑但保留决定结果；note 用于人工检查
        reasons.append("mb_suspect_cached")

    return {
        **row,
        "videoId": yt_video or row.get("videoId", ""),
        "release_date": release_date,
        "date_source": date_source,
        "note": ";".join(reasons),
        "mb_date": mb_date,
        "yt_album_year": yt_year,
        "qq_time_public": qq_time,
    }


def sort_songs(songs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key_fn(r: Dict[str, Any]):
        rd = r.get("release_date") or ""
        if rd:
            return (rd, r.get("title", ""))
        # 无日期视为最老
        return ("0000-01-01", r.get("title", ""))

    return sorted(songs, key=key_fn)


def _passes_filter(release_date: str, filter_before: Optional[str], filter_after: Optional[str]) -> bool:
    """过滤条件：发布日期早于 filter_before，且晚于 filter_after（均为含边界，ISO 字符串比较即可）。无日期则不满足过滤。"""
    if not release_date:
        return False
    if filter_before and release_date > filter_before:
        return False
    if filter_after and release_date < filter_after:
        return False
    return True


def build_local_csv(
    songs: Iterable[Dict[str, Any]],
    cache: SongCache,
    out_path: Path,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    filter_before: Optional[str] = None,
    filter_after: Optional[str] = None,
) -> None:
    overrides = overrides or {}
    selected = []
    for s in songs:
        row = choose_date(s, cache, overrides)
        if filter_before or filter_after:
            if not _passes_filter(row.get("release_date", ""), filter_before, filter_after):
                continue
        selected.append(row)
    selected = sort_songs(selected)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "title",
        "artists",
        "album",
        "album_year",
        "time_public",
        "videoId",
        "release_date",
        "source",
        "date_source",
        "note",
        "mb_date",
        "yt_album_year",
        "qq_time_public",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in selected:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


__all__ = ["build_local_csv", "choose_date", "sort_songs"]
