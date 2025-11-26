"""YTMusic 认证与健康检查工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ytmusicapi import OAuthCredentials, YTMusic


def build_from_headers(headers_path: Path) -> YTMusic:
    """使用浏览器 headers_auth.json 创建客户端。"""
    return YTMusic(str(headers_path))


def build_from_oauth(token_path: Path, client_path: Path) -> YTMusic:
    """使用 oauth.json + oauth_client 信息创建客户端。"""
    client_info: Dict[str, Any] = json.loads(client_path.read_text())
    credentials = OAuthCredentials(
        client_id=client_info["client_id"],
        client_secret=client_info["client_secret"],
    )
    return YTMusic(str(token_path), oauth_credentials=credentials)


def health_check(yt: YTMusic, sample_playlist_id: Optional[str] = None) -> Dict[str, Any]:
    """简单健康检查：读取少量歌单并可选读取一个已知歌单。"""
    status: Dict[str, Any] = {"ok": False, "playlists": 0, "error": None}
    try:
        playlists = yt.get_library_playlists(limit=1) or []
        status["playlists"] = len(playlists)
        if sample_playlist_id:
            yt.get_playlist(sample_playlist_id, limit=1)
        status["ok"] = True
    except Exception as e:  # noqa: BLE001
        status["error"] = str(e)
    return status


__all__ = ["build_from_headers", "build_from_oauth", "health_check"]
