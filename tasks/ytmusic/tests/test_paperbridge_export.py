import csv
import json
import tempfile
import unittest
from pathlib import Path

from tasks.ytmusic.src.core.paperbridge_export import build_library, playlist_slug

FIELDS = ["title", "artists", "release_date", "videoId"]


class PaperbridgeExportTest(unittest.TestCase):
    def test_build_library_merges_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "zr.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerow({"title": "红豆", "artists": "王菲", "release_date": "1998-10-02", "videoId": "AAAAAAAAAAA"})
                w.writerow({"title": "红豆", "artists": "王菲", "release_date": "1998-10-02", "videoId": "AAAAAAAAAAA"})
                w.writerow({"title": "遇", "artists": "ai mini", "release_date": "2004-07-05", "videoId": ""})
            (root / "playlists.json").write_text(json.dumps([
                {"title": "Liked Music", "id": "LM", "path": "."},
                {"title": "昨日重现", "id": "PLx", "path": "zr.csv"},
            ]), encoding="utf-8")
            (root / "cands.json").write_text(json.dumps({"昨日重现": {"红豆|王菲": {
                "ref_length_s": 256,
                "current": {"label": "MV", "kind": "original_mv"},
                "candidates": [
                    {"video_id": "AAAAAAAAAAA", "label": "重复", "kind": "original_mv"},
                    {"video_id": "BBBBBBBBBBB", "label": "原唱录音室", "kind": "original_studio"},
                ],
            }}}, ensure_ascii=False), encoding="utf-8")

            library = build_library(root / "playlists.json", root / "cands.json", root)
            self.assertEqual(library["schema_version"], 1)
            [playlist] = library["playlists"]
            self.assertEqual((playlist["id"], playlist["yt_playlist_id"]), ("zuori", "PLx"))
            self.assertEqual(len(playlist["tracks"]), 2)
            hongdou, yu = playlist["tracks"]
            self.assertEqual(hongdou["current"]["video_id"], "AAAAAAAAAAA")
            self.assertEqual([c["video_id"] for c in hongdou["candidates"]], ["BBBBBBBBBBB"])
            self.assertIsNone(yu["video_id"])
            self.assertEqual(yu["candidates"], [])

    def test_slug(self) -> None:
        self.assertEqual(playlist_slug("Yesterday once more"), "yom")
        self.assertEqual(playlist_slug("Billboard 2025"), "billboard-2025")
        self.assertTrue(playlist_slug("记忆中的声音").startswith("pl-"))


if __name__ == "__main__":
    unittest.main()
