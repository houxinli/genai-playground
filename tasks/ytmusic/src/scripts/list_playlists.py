"""列出库内歌单，便于确认 playlistId。"""

from __future__ import annotations

from pathlib import Path
import sys

# 确保 repo 根目录在路径中
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tasks.ytmusic.src.ytmusic.client import get_client


def main() -> None:
    yt = get_client("headers", headers_path=Path("tasks/ytmusic/config/headers.json"))
    pls = yt.get_library_playlists(limit=200) or []
    for p in pls:
        print(f"{p.get('title')} | id={p.get('playlistId')} | count={p.get('count')}")


if __name__ == "__main__":
    main()
