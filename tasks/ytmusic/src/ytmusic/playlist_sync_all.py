"""批量同步：从 playlists.json 的列表映射同步 local CSV 到 YT。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from tasks.ytmusic.src.logging.logger import get_logger

from .client import get_client
from .sync_pipeline import apply_csv_to_playlist


@dataclass
class PlaylistEntry:
    title: str
    id: Optional[str]  # playlistId，可为空表示需要创建
    path: Path         # 对应的 local CSV 路径


def load_playlists_json(path: Path) -> List[PlaylistEntry]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    entries: List[PlaylistEntry] = []
    if isinstance(data, list):
        for item in data:
            entries.append(
                PlaylistEntry(
                    title=item.get("title", ""),
                    id=item.get("id"),
                    path=Path(item.get("path")),
                )
            )
    elif isinstance(data, dict):
        # 兼容旧格式 {title: id}
        for title, pid in data.items():
            entries.append(PlaylistEntry(title=title, id=pid, path=Path(f"tasks/ytmusic/data/local/{title}.csv")))
    return entries


def save_playlists_json(path: Path, entries: List[PlaylistEntry]) -> None:
    payload = [{"title": e.title, "id": e.id, "path": str(e.path)} for e in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def fetch_all_playlists_from_yt(headers: Path, playlists_json: Path, auth_mode: str = "headers") -> List[PlaylistEntry]:
    """
    从 YT 拉取所有歌单，更新 playlists.json 的 title/id。
    path 字段沿用原文件（如果已有），否则留空。
    """
    logger = get_logger(__name__)
    yt = get_client(auth_mode, headers_path=headers if auth_mode == "headers" else None)
    library = yt.get_library_playlists(limit=500) or []
    logger.info("从 YT 获取到歌单数量=%s", len(library))
    existing = {e.title: e for e in load_playlists_json(playlists_json)}

    if not library:
        logger.warning("未从 YT 获取到任何歌单，保留原 playlists.json 不做覆盖。")
        return list(existing.values())

    updated: List[PlaylistEntry] = []
    for p in library:
        title = p.get("title") or ""
        pid = p.get("playlistId") or ""
        path = existing.get(title, PlaylistEntry(title, pid, Path(""))).path
        updated.append(PlaylistEntry(title=title, id=pid, path=path))

    save_playlists_json(playlists_json, updated)
    logger.info("已刷新 playlists.json，数量=%s", len(updated))
    return updated


def sync_local_playlists_to_yt(
    headers: Path,
    playlists_json: Path,
    cache_path: Path,
    log_dir: Path,
    auth_mode: str = "headers",
) -> List[PlaylistEntry]:
    logger = get_logger(__name__, log_dir / "playlist_sync_all.log")
    yt = get_client(auth_mode, headers_path=headers if auth_mode == "headers" else None)
    entries = load_playlists_json(playlists_json)

    # 获取现有歌单映射
    library_map: Dict[str, str] = {p.get("title", ""): p.get("playlistId", "") for p in yt.get_library_playlists(limit=500) or []}

    updated_entries: List[PlaylistEntry] = []
    for entry in entries:
        csv_path = entry.path
        # 注意 Path("") 和 Path(".") 都指向当前目录且 exists() 为真，必须用 is_file 判断
        if not csv_path.is_file():
            logger.warning("跳过，不是有效的 CSV 文件: %s (title=%s)", csv_path, entry.title)
            continue

        pid = entry.id
        if not pid:
            # 尝试匹配现有歌单
            if entry.title in library_map:
                pid = library_map[entry.title]
            else:
                pid = yt.create_playlist(entry.title, description="", privacy_status="PRIVATE")
                logger.info("创建歌单 %s -> %s", entry.title, pid)

        summary = apply_csv_to_playlist(
            headers=headers,
            csv_path=csv_path,
            playlist_id=pid,
            cache_path=cache_path,
            yt_limit=5,
            log_path=log_dir / f"update_playlist_{entry.title}.log",
            auth_mode=auth_mode,
            write_back=False,
        )
        logger.info("同步 %s -> %s summary=%s", entry.title, pid, summary)
        updated_entries.append(PlaylistEntry(title=entry.title, id=pid, path=csv_path))

    save_playlists_json(playlists_json, updated_entries)
    return updated_entries


__all__ = ["sync_local_playlists_to_yt", "PlaylistEntry", "load_playlists_json", "save_playlists_json"]
