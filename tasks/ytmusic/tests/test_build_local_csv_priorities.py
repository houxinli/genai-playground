import tempfile
import csv
from pathlib import Path
import unittest

from tasks.ytmusic.src.build_local_csv import build_local_csv
from tasks.ytmusic.src.cache_utils import SongCache


class BuildLocalCsvPriorityTest(unittest.TestCase):
    def test_priority_mb_over_yt_over_fallback(self) -> None:
        songs = [
            {"title": "Song", "artists": "Artist", "album_year": "2010", "time_public": "", "album": "", "videoId": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            cache = SongCache(cache_path)
            cache.set("Song|Artist", "yt", "album_year", "2015")
            cache.set("Song|Artist", "mb", "release_date", "2000-01-01")
            cache.save()

            out_path = Path(tmp) / "out.csv"
            build_local_csv(songs, cache, out_path, overrides={})
            with out_path.open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["release_date"], "2000-01-01")
            self.assertEqual(rows[0]["yt_album_year"], "2015")
            self.assertEqual(rows[0]["mb_date"], "2000-01-01")


if __name__ == "__main__":
    unittest.main()
