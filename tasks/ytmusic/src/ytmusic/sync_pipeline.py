"""从 CSV 同步到 YT 播放列表的管线。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.core.normalize import make_key
from tasks.ytmusic.src.logging.logger import get_logger

from .cache import ensure_yt_cache_for_song
from .client import get_client
from .playlists import sync_playlist


def sort_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key_fn(r: Dict[str, Any]) -> tuple:
        if r.get("release_date"):
            return (0, r["release_date"], r.get("title", ""))
        album_year = r.get("album_year") or r.get("time_public")
        if album_year:
            return (1, str(album_year), r.get("title", ""))
        return (2, r.get("title", ""))

    return sorted(rows, key=key_fn)


def apply_csv_to_playlist(
    headers: Path,
    csv_path: Path,
    playlist_id: str,
    *,
    cache_path: Path,
    yt_limit: int = 4,
    log_path: Optional[Path] = None,
    auth_mode: str = "headers",
    write_back: bool = False,
) -> Dict[str, Any]:
    """
    读取 CSV -> 补齐 videoId（缺失时搜索）-> 排序 -> 同步到指定 playlist。
    返回 summary，包括同步结果与总数。
    """
    logger = get_logger(__name__, log_path)
    logger.info("开始同步 CSV -> playlist csv=%s playlist_id=%s auth=%s", csv_path, playlist_id, auth_mode)
    try:
        yt = get_client(auth_mode, headers_path=headers if auth_mode == "headers" else None)
    except Exception as e:  # noqa: BLE001
        logger.error("创建 YT 客户端失败: %s", e)
        raise
    cache = SongCache(cache_path)

    rows = list(csv.DictReader(csv_path.open()))
    enriched: List[Dict[str, Any]] = []
    log_entries: List[Dict[str, Any]] = []

    logger.info("读取 CSV 行数=%s", len(rows))
    for r in rows:
        title = r.get("title", "")
        artists = r.get("artists", "")
        video_id = r.get("videoId", "")
        key = make_key(title, artists)

        if not video_id:
            result = ensure_yt_cache_for_song(r, cache, yt, yt_limit=yt_limit, logger=logger)
            video_id = result.get("videoId") or ""
            status = result.get("status", "missing")
        else:
            status = "existing"

        enriched_row = {**r, "videoId": video_id}
        enriched.append(enriched_row)
        log_entries.append({**enriched_row, "status": status})

    sorted_rows = sort_rows(enriched)
    video_ids = [r.get("videoId") for r in sorted_rows if r.get("videoId")]
    logger.info("准备写入条目: 总行=%s 有videoId=%s", len(sorted_rows), len(video_ids))
    try:
        summary = sync_playlist(yt, playlist_id, video_ids)
    except Exception as e:  # noqa: BLE001
        logger.error("同步歌单失败 playlist=%s err=%s", playlist_id, e)
        raise
    summary.update({"total_rows": len(sorted_rows), "with_videoId": len(video_ids)})

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as f:
            for e in log_entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.write(json.dumps({"summary": summary}, ensure_ascii=False) + "\n")
        logger.info("写入同步日志: %s", log_path)

    logger.info(
        "同步完成 playlist=%s 总行=%s 有videoId=%s 新增=%s 移除=%s 错误=%s",
        playlist_id,
        summary.get("total_rows"),
        summary.get("with_videoId"),
        summary.get("added"),
        summary.get("removed"),
        summary.get("errors"),
    )

    cache.save()
    if write_back:
        fieldnames = sorted({k for row in enriched for k in row.keys()})
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in enriched:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        logger.info("已将补齐的 videoId 写回 CSV: %s", csv_path)

    return summary


__all__ = ["apply_csv_to_playlist", "sort_rows"]
