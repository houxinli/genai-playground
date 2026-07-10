"""拉取 QQ 音乐线上歌单(公开接口,无需登录)。"""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from tasks.ytmusic.src.core.normalize import normalize_artists, normalize_title

FCG_URL = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"


def fetch_playlist_raw(disstid: str, timeout: float = 10.0) -> Dict[str, Any]:
    params = urllib.parse.urlencode({
        "type": 1, "json": 1, "utf8": 1, "onlysong": 0,
        "disstid": disstid, "format": "json", "song_begin": 0, "song_num": 1000,
    })
    req = urllib.request.Request(
        f"{FCG_URL}?{params}",
        headers={"Referer": "https://y.qq.com/", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_playlist(raw: Dict[str, Any]) -> Dict[str, Any]:
    """返回 {name, songs:[{title, artists, album, song_mid, song_id, interval_seconds}]}。
    title/artists 已按 qq_extractor 同款规则规范化,保证 key 与既有数据一致。"""
    cd = (raw.get("cdlist") or [{}])[0]
    songs: List[Dict[str, str]] = []
    for s in cd.get("songlist") or []:
        title = normalize_title(s.get("songname", ""))
        artists = normalize_artists(" / ".join(x.get("name", "") for x in s.get("singer", []) or []))
        songs.append({
            "title": title,
            "artists": artists,
            "album": s.get("albumname", "") or "",
            "album_mid": s.get("albummid", "") or "",
            "song_mid": s.get("songmid", "") or "",
            "song_id": str(s.get("songid", "") or ""),
            "interval_seconds": str(s.get("interval", "") or ""),
        })
    return {"name": cd.get("dissname", ""), "songs": songs}


def write_qq_csv(songs: List[Dict[str, str]], out_path: Path) -> None:
    """写成与 data/qqmusic/*.csv 一致的导出格式。"""
    fieldnames = ["index", "title", "artists", "album", "album_mid", "song_mid", "song_id", "interval_seconds"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, s in enumerate(songs, start=1):
            writer.writerow({"index": i, **{k: s.get(k, "") for k in fieldnames[1:]}})


__all__ = ["fetch_playlist_raw", "parse_playlist", "write_qq_csv"]
