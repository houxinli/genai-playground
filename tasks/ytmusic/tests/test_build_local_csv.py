import csv
import json
import tempfile
import unittest
from pathlib import Path

from tasks.ytmusic.src.build_local_csv import build_local_csv
from tasks.ytmusic.src.cache_utils import SongCache


class BuildLocalCsvTest(unittest.TestCase):
    def test_choose_and_sort(self) -> None:
        songs = [
            {"title": "B", "artists": "Artist2", "album_year": "2005", "time_public": "", "album": "", "videoId": ""},
            {"title": "A", "artists": "Artist1", "album_year": "", "time_public": "", "album": "", "videoId": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            cache = SongCache(cache_path)
            cache.set("A|Artist1", "mb", "release_date", "2003-01-01")
            cache.save()

            out_path = Path(tmp) / "out.csv"
            build_local_csv(songs, cache, out_path, overrides={})

            with out_path.open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            # 排序：A(2003) 在前，B(2005 fallback) 在后
            self.assertEqual(rows[0]["title"], "A")
            self.assertEqual(rows[0]["release_date"], "2003-01-01")
            self.assertEqual(rows[1]["release_date"], "2005-12-31")

    def test_filter_before_after(self) -> None:
        songs = [
            {"title": "Old", "artists": "A", "album_year": "", "time_public": "", "album": "", "videoId": ""},
            {"title": "New", "artists": "B", "album_year": "", "time_public": "", "album": "", "videoId": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            cache = SongCache(cache_path)
            cache.set("Old|A", "mb", "release_date", "1999-01-01")
            cache.set("New|B", "mb", "release_date", "2010-01-01")
            cache.save()

            out_path = Path(tmp) / "out.csv"
            # 仅保留 2000 年之前的
            build_local_csv(songs, cache, out_path, overrides={}, filter_before="2000-01-01")
            with out_path.open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Old")

    def test_qq_time_public_as_fallback(self) -> None:
        songs = [
            {"title": "C", "artists": "Artist3", "album_year": "", "time_public": "", "album": "", "videoId": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            cache = SongCache(cache_path)
            cache.set("C|Artist3", "qq", "time_public", "2001-05-06")
            cache.save()

            out_path = Path(tmp) / "out.csv"
            build_local_csv(songs, cache, out_path, overrides={})
            with out_path.open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["release_date"], "2001-12-31")


if __name__ == "__main__":
    unittest.main()
