from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .client import get_client
from .sync_pipeline import apply_csv_to_playlist


def load_playlists_json(path: Path) -> Dict[str, str]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def save_playlists_json(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def list_yt_playlists(yt) -> Dict[str, str]:
    playlists = yt.get_library_playlists(limit=500) or []
    return {p.get("title", ""): p.get("playlistId", "") for p in playlists if p.get("playlistId")}


def ensure_playlist(yt, name: str, mapping: Dict[str, str], library_map: Dict[str, str]) -> str:
    if name in mapping:
        return mapping[name]
    if name in library_map:
        return library_map[name]
    # create new
    playlist_id = yt.create_playlist(name, description="")
    return playlist_id


def sync_local_playlists_to_yt(
    headers: Path,
    local_dir: Path,
    playlists_json: Path,
    cache_path: Path,
    log_dir: Path,
) -> Dict[str, str]:
    yt = get_client("headers", headers_path=headers)
    mapping = load_playlists_json(playlists_json)
    library_map = list_yt_playlists(yt)

    updated_mapping = dict(mapping)
    local_dir = local_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    for csv_path in local_dir.glob("*.csv"):
        name = csv_path.stem
        playlist_id = ensure_playlist(yt, name, updated_mapping, library_map)
        updated_mapping[name] = playlist_id
        apply_csv_to_playlist(
            headers=headers,
            csv_path=csv_path,
            playlist_id=playlist_id,
            cache_path=cache_path,
            yt_limit=5,
            search_missing=False,
            log_path=log_dir / f"update_playlist_{name}.log",
        )
        print(f"synced {name} -> {playlist_id}")

    save_playlists_json(playlists_json, updated_mapping)
    return updated_mapping


__all__ = ["sync_local_playlists_to_yt"]
