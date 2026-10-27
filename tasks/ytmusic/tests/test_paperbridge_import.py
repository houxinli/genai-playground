import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tasks.ytmusic.src.core.paperbridge_import import import_library


class PaperbridgeImportTest(unittest.TestCase):
    def test_writes_video_ids_overrides_cache_and_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fields = ["title", "artists", "release_date", "videoId", "note"]
            with (root / "zr.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerow({"title": "毒蘑菇", "artists": "周笔畅", "release_date": "2006-08-12", "videoId": "OLDOLDOLD01", "note": "x"})
                w.writerow({"title": "江南", "artists": "林俊杰", "release_date": "2004-06-04", "videoId": "SAMESAME001", "note": ""})
            (root / "playlists.json").write_text(json.dumps([{"title": "昨日重现", "id": "PL", "path": "zr.csv"}]), encoding="utf-8")
            (root / "overrides.json").write_text(json.dumps({"毒蘑菇|周笔畅": {"release_date": "2006-08-12", "videoId": "OLDOLDOLD01"}}), encoding="utf-8")
            (root / "cache.json").write_text(json.dumps({"毒蘑菇|周笔畅": {"mb": {}, "yt": {"videoId": "OLDOLDOLD01"}}}), encoding="utf-8")
            library = {"playlists": [{"name": "昨日重现", "tracks": [
                {"key": "毒蘑菇|周笔畅", "video_id": "NEWNEWNEW01",
                 "current": {"video_id": "NEWNEWNEW01", "label": "原唱录音室", "kind": "original_studio"},
                 "candidates": [{"video_id": "OLDOLDOLD01", "label": "许仲文翻唱", "kind": "cover"}]},
                {"key": "江南|林俊杰", "video_id": "SAMESAME001", "candidates": []},
                {"key": "新歌|某人", "video_id": None, "candidates": []},
            ]}]}
            kwargs = dict(playlists_json=root / "playlists.json", repo_root=root, overrides_path=root / "overrides.json",
                          cache_path=root / "cache.json", candidates_path=root / "cands.json", today=date(2026, 10, 27))

            preview = import_library(library, dry_run=True, **kwargs)
            self.assertEqual(len(preview["changes"]), 1)
            self.assertIn("OLDOLDOLD01", (root / "zr.csv").read_text(encoding="utf-8"))

            result = import_library(library, **kwargs)
            self.assertEqual(result["changes"][0]["to"], "NEWNEWNEW01")
            self.assertEqual(len(result["unmatched"]), 1)
            rows = list(csv.DictReader((root / "zr.csv").open(encoding="utf-8")))
            self.assertEqual([r["videoId"] for r in rows], ["NEWNEWNEW01", "SAMESAME001"])
            self.assertEqual(rows[0]["note"], "x")
            override = json.loads((root / "overrides.json").read_text(encoding="utf-8"))["毒蘑菇|周笔畅"]
            self.assertEqual((override["videoId"], override["release_date"]), ("NEWNEWNEW01", "2006-08-12"))
            self.assertIn("2026-10-27 paperbridge", override["reason"])
            cache = json.loads((root / "cache.json").read_text(encoding="utf-8"))["毒蘑菇|周笔畅"]
            self.assertEqual(cache["yt"]["videoId"], "NEWNEWNEW01")
            cands = json.loads((root / "cands.json").read_text(encoding="utf-8"))["昨日重现"]["毒蘑菇|周笔畅"]
            self.assertEqual(cands["current"]["label"], "原唱录音室")
            self.assertEqual(cands["candidates"][0]["video_id"], "OLDOLDOLD01")


if __name__ == "__main__":
    unittest.main()
