from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List

from tasks.ytmusic.src.core.normalize import make_key, normalize_artists, normalize_title


QQ_FIELDS = [
    "title",
    "artists",
    "album",
    "album_mid",
    "song_mid",
    "song_id",
    "interval_seconds",
]


def _normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    title = row.get("title", "").strip()
    artists = row.get("artists", "").strip()
    return {
        "title": normalize_title(title),
        "artists": normalize_artists(artists),
        "album": row.get("album", "").strip(),
        "album_year": row.get("album_year", "").strip(),
        "time_public": row.get("time_public", "").strip(),
        "videoId": row.get("videoId", "").strip(),
        "album_mid": row.get("album_mid", "").strip(),
        "song_mid": row.get("song_mid", "").strip(),
        "song_id": row.get("song_id", "").strip(),
        "interval_seconds": row.get("interval_seconds", "").strip(),
        "source": "qq",
    }


def extract_from_csv(csv_path: Path, dedupe: bool = True) -> List[Dict[str, str]]:
    """
    从 QQ 音乐导出的 csv 读取并规范化为通用歌曲列表。
    默认按 title|artists 去重。
    """
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    seen = set()
    songs: List[Dict[str, str]] = []
    for r in rows:
        song = _normalize_row(r)
        key = make_key(song["title"], song["artists"])
        if dedupe and key in seen:
            continue
        seen.add(key)
        songs.append(song)
    return songs


def write_songs_csv(songs: Iterable[Dict[str, str]], out_path: Path) -> None:
    """将规范化后的歌曲列表写入 CSV。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["title", "artists", "album", "album_year", "time_public", "videoId", "release_date", "source"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for song in songs:
            row = {**song}
            row.setdefault("release_date", "")
            row.setdefault("source", "qq")
            writer.writerow({k: row.get(k, "") for k in fieldnames})


__all__ = ["extract_from_csv", "write_songs_csv", "QQ_FIELDS"]
