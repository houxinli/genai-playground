"""播放列表相关操作。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError
from tasks.ytmusic.src.logging.logger import get_logger


def list_playlists(yt: YTMusic, limit: int = 200) -> List[Dict[str, Any]]:
    return yt.get_library_playlists(limit=limit) or []


def get_playlist(yt: YTMusic, playlist_id: str, limit: int = 6000) -> Dict[str, Any]:
    return yt.get_playlist(playlist_id, limit=limit) or {}


def _remove_all(yt: YTMusic, playlist_id: str, items: List[Dict[str, Any]], batch_size: int = 50, logger=None) -> None:
    logger = logger or get_logger(__name__)
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        try:
            yt.remove_playlist_items(playlist_id, batch)
        except Exception as e:  # noqa: BLE001
            logger.warning("批量移除失败, 尝试逐条: %s", e)
            for it in batch:
                try:
                    yt.remove_playlist_items(playlist_id, [it])
                except Exception as e2:  # noqa: BLE001
                    logger.error("逐条移除失败 setVideoId=%s err=%s", it.get("setVideoId"), e2)


def _add_all(yt: YTMusic, playlist_id: str, video_ids: Iterable[str], batch_size: int = 50, logger=None) -> Dict[str, int]:
    logger = logger or get_logger(__name__)
    summary = {"added": 0, "errors": 0}
    batch: List[str] = []
    for vid in video_ids:
        if not vid:
            continue
        batch.append(vid)
        if len(batch) >= batch_size:
            try:
                yt.add_playlist_items(playlist_id, batch, duplicates=True)
                summary["added"] += len(batch)
            except YTMusicServerError as e:
                logger.warning("批量添加失败，降级逐条: %s", e)
                for v in batch:
                    try:
                        yt.add_playlist_items(playlist_id, [v], duplicates=True)
                        summary["added"] += 1
                    except YTMusicServerError as e2:
                        summary["errors"] += 1
                        logger.error("逐条添加失败 videoId=%s err=%s", v, e2)
            batch.clear()
    if batch:
        try:
            yt.add_playlist_items(playlist_id, batch, duplicates=True)
            summary["added"] += len(batch)
        except YTMusicServerError as e:
            logger.warning("批量添加(尾批)失败，降级逐条: %s", e)
            for v in batch:
                try:
                    yt.add_playlist_items(playlist_id, [v], duplicates=True)
                    summary["added"] += 1
                except YTMusicServerError as e2:
                    summary["errors"] += 1
                    logger.error("逐条添加失败 videoId=%s err=%s", v, e2)
    return summary


def sync_playlist(
    yt: YTMusic,
    playlist_id: str,
    video_ids: List[str],
    *,
    clear_first: bool = True,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    将目标 playlist 重建为给定的 video_ids 顺序。
    简化策略：清空后追加；失败时逐条 fallback。
    """
    logger = get_logger(__name__)
    summary: Dict[str, Any] = {"target": len(video_ids), "removed": 0, "added": 0, "errors": 0}
    if clear_first:
        current = get_playlist(yt, playlist_id, limit=6000)
        items = [
            {"setVideoId": t.get("setVideoId"), "videoId": t.get("videoId")}
            for t in current.get("tracks", []) or []
            if t.get("setVideoId") and t.get("videoId")
        ]
        summary["removed"] = len(items)
        if items:
            logger.info("清空歌单 %s 条目=%s", playlist_id, len(items))
            _remove_all(yt, playlist_id, items, batch_size=batch_size, logger=logger)

    # 添加阶段，批量失败则逐条降级
    add_summary = _add_all(yt, playlist_id, video_ids, batch_size=batch_size, logger=logger)
    summary["added"] += add_summary["added"]
    summary["errors"] += add_summary["errors"]
    logger.info(
        "同步歌单完成 playlist=%s 目标=%s 清空=%s 新增=%s 错误=%s",
        playlist_id,
        len(video_ids),
        summary.get("removed"),
        summary.get("added"),
        summary.get("errors"),
    )

    return summary


__all__ = ["list_playlists", "get_playlist", "sync_playlist"]
