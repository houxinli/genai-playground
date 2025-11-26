import unittest
from pathlib import Path
from typing import Dict, List

from tasks.ytmusic.src.cache_utils import SongCache
from tasks.ytmusic.src.mb_cache_updater import update_mb_cache


def fake_search(title: str, artists: str, limit: int) -> List[Dict]:
    # 简化：对特定标题返回固定结果，其余返回空
    if title == "晴天":
        return [
            {"first-release-date": "2003-05-01", "releases": []},
            {"first-release-date": "2004-01-01", "releases": []},
        ]
    return []


class MbCacheUpdaterTest(unittest.TestCase):
    def test_update_cache_and_fallback(self) -> None:
        cache_path = Path("/tmp/test_mb_cache.json")
        if cache_path.exists():
            cache_path.unlink()
        cache = SongCache(cache_path)
        songs = [
            {"title": "晴天", "artists": "周杰伦", "album_year": "2003", "time_public": "", "album": ""},
            {"title": "未知", "artists": "歌手", "album_year": "", "time_public": "", "album": ""},
        ]

        update_mb_cache(
            songs,
            cache,
            mb_limit=3,
            max_lookups=10,
            search_fn=fake_search,
            log_path=Path("/tmp/test_mb_log.ndjson"),
        )

        key = "晴天|周杰伦"
        self.assertEqual(cache.get(key, "mb", "release_date"), "2003-05-01")
        fallback_key = "未知|歌手"
        # 没有 MB 命中也没有 fallback，应为空字符串
        self.assertEqual(cache.get(fallback_key, "mb", "release_date"), "")


if __name__ == "__main__":
    unittest.main()
