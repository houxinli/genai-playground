import unittest

from tasks.ytmusic.src.ytmusic.sync_pipeline import ordered_video_ids, sort_rows


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

    def test_ordered_video_ids_newest_first_and_dedupe(self) -> None:
        rows = [
            {"title": "老", "release_date": "2000-01-01", "album_year": "", "time_public": "", "videoId": "old"},
            {"title": "新", "release_date": "2010-01-01", "album_year": "", "time_public": "", "videoId": "new"},
            {"title": "重复", "release_date": "2005-01-01", "album_year": "", "time_public": "", "videoId": "old"},
            {"title": "无视频", "release_date": "2001-01-01", "album_year": "", "time_public": "", "videoId": ""},
        ]
        self.assertEqual(ordered_video_ids(rows), ["old", "new"])
        self.assertEqual(ordered_video_ids(rows, newest_first=True), ["new", "old"])


if __name__ == "__main__":
    unittest.main()
