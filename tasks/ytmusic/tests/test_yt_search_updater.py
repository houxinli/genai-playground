import unittest
from pathlib import Path
from typing import Dict, List

from tasks.ytmusic.src.core.cache_utils import SongCache
from tasks.ytmusic.src.ytmusic.yt_search_updater import update_yt_cache


class DummyYT:
    def __init__(self, results: Dict[str, List[Dict]]):
        self.results = results


def fake_search(yt, title: str, artists: str, limit: int) -> List[Dict]:
    key = f"{title}|{artists}"
    return yt.results.get(key, [])


class YtSearchUpdaterTest(unittest.TestCase):
    def test_updates_cache(self) -> None:
        songs = [{"title": "Song", "artists": "Artist"}]
        results = {
            "Song|Artist": [{"videoId": "vid123", "album": {"year": "2010"}}],
        }
        cache_path = Path("/tmp/test_yt_cache.json")
        if cache_path.exists():
            cache_path.unlink()
        cache = SongCache(cache_path)
        yt = DummyYT(results)

        update_yt_cache(
            songs,
            cache,
            headers=Path("/dev/null"),  # unused in fake search
            search_fn=lambda _yt, t, a, l: fake_search(yt, t, a, l),
            max_lookups=5,
            log_path=None,
        )

        self.assertEqual(cache.get("Song|Artist", "yt", "videoId"), "vid123")
        self.assertEqual(cache.get("Song|Artist", "yt", "album_year"), "2010")


if __name__ == "__main__":
    unittest.main()
