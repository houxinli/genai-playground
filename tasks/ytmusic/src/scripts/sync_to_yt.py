"""快捷同步脚本：从本地 CSV 同步到指定 YT 歌单。"""

from __future__ import annotations

from pathlib import Path
import sys

# 确保 repo 根目录在 sys.path
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tasks.ytmusic.src.ytmusic.sync_pipeline import apply_csv_to_playlist


def main() -> None:
    # 默认参数：可按需修改
    headers = Path("tasks/ytmusic/config/headers.json")
    csv_path = Path("tasks/ytmusic/data/local/中国风.csv")
    playlist_id = "PLdw3lRqU3xktPI7BOQUHNGU6wO0rN99f-"
    cache_path = Path("tasks/ytmusic/data/cache_mb.json")
    log_path = Path("tasks/ytmusic/logs/update_playlist_中国风.log")

    summary = apply_csv_to_playlist(
        headers=headers,
        csv_path=csv_path,
        playlist_id=playlist_id,
        cache_path=cache_path,
        yt_limit=5,
        search_missing=False,
        log_path=log_path,
        auth_mode="headers",
    )
    print("同步完成 summary =", summary)


if __name__ == "__main__":
    main()
