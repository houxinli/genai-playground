from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .cache_utils import SongCache
from .normalize import make_key


def fetch_song_detail(song_mid: str, timeout: float = 8.0) -> Dict:
    """
    调用 QQ 音乐 song_detail 接口，返回完整 JSON。
    """
    payload = {
        "songinfo": {
            "method": "get_song_detail_yqq",
            "param": {"song_mid": song_mid},
            "module": "music.pf_song_detail_svr",
        }
    }
    params = urllib.parse.urlencode({"format": "json", "data": json.dumps(payload)})
    url = f"https://u.y.qq.com/cgi-bin/musicu.fcg?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def extract_time_public(detail: Dict) -> Optional[str]:
    track = detail.get("songinfo", {}).get("data", {}).get("track_info", {}) or {}
    tp = track.get("time_public")
    if tp:
        return tp
    album = track.get("album", {}) or {}
    tp_album = album.get("time_public")
    return tp_album


def update_qq_times(
    songs: Sequence[Dict[str, str]],
    cache: SongCache,
    *,
    log_path: Path,
    max_lookups: int = 2000,
    refresh_existing: bool = False,
    timeout: float = 8.0,
) -> None:
    """
    使用 song_mid 批量获取 QQ time_public，写入缓存 qq.time_public。
    """
    log_entries: List[str] = []
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    lookups = 0
    for idx, song in enumerate(songs):
        mid = song.get("song_mid") or song.get("song_mid".lower()) or ""
        title = song.get("title", "")
        artists = song.get("artists", "")
        key = make_key(title, artists)

        cached = cache.get(key, "qq", "time_public")
        if cached and not refresh_existing:
            log_entries.append(json.dumps({"index": idx, "key": key, "time_public": cached, "source": "cache"}))
            continue

        if not mid:
            log_entries.append(json.dumps({"index": idx, "key": key, "error": "missing_song_mid"}))
            continue

        if lookups >= max_lookups:
            log_entries.append(json.dumps({"index": idx, "key": key, "error": "max_lookups_reached"}))
            continue

        try:
            detail = fetch_song_detail(mid, timeout=timeout)
            tp = extract_time_public(detail) or ""
            cache.set(key, "qq", "time_public", tp)
            cache.set(key, "qq", "raw", detail)
            log_entries.append(json.dumps({"index": idx, "key": key, "time_public": tp, "source": "qq_api"}))
        except Exception as exc:
            log_entries.append(json.dumps({"index": idx, "key": key, "error": f"qq_fetch_fail:{exc}"}))
        lookups += 1

    cache.save()
    if log_path:
        log_path.write_text("\n".join(log_entries) + "\n")


__all__ = ["update_qq_times"]
