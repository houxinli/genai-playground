import unittest

from tasks.ytmusic.src.ytmusic.sync_pipeline import sort_rows


class UpdatePlaylistSortTest(unittest.TestCase):
    def test_sorting_prefers_release_date_then_year(self) -> None:
        rows = [
            {"title": "C", "release_date": "", "album_year": "2001", "time_public": "", "videoId": "c"},
            {"title": "A", "release_date": "2000-01-01", "album_year": "", "time_public": "", "videoId": "a"},
            {"title": "B", "release_date": "", "album_year": "", "time_public": "", "videoId": "b"},
        ]
        sorted_rows = sort_rows(rows)
        # release_date > album_year > missing
        self.assertEqual([r["title"] for r in sorted_rows], ["A", "C", "B"])


if __name__ == "__main__":
    unittest.main()
