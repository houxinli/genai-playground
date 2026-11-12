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
                {"key": "新歌|某人", "title": "新歌", "artists": "某人", "video_id": None, "candidates": []},
            ]}]}
            kwargs = dict(playlists_json=root / "playlists.json", repo_root=root, overrides_path=root / "overrides.json",
                          cache_path=root / "cache.json", candidates_path=root / "cands.json", today=date(2026, 10, 27))

            preview = import_library(library, dry_run=True, **kwargs)
            self.assertEqual(len(preview["changes"]), 1)
            self.assertIn("OLDOLDOLD01", (root / "zr.csv").read_text(encoding="utf-8"))

            result = import_library(library, **kwargs)
            self.assertEqual(result["changes"][0]["to"], "NEWNEWNEW01")
            self.assertEqual(result["unmatched"], [])
            # 服务器上网页加的歌（没日期）进 CSV，排在最后。
            self.assertEqual([m["op"] for m in result["membership"]], ["add"])
            rows = list(csv.DictReader((root / "zr.csv").open(encoding="utf-8")))
            self.assertEqual([r["videoId"] for r in rows], ["SAMESAME001", "NEWNEWNEW01", ""])
            rows = rows[1:2] + rows[:1]
            self.assertEqual(rows[0]["note"], "x")
            override = json.loads((root / "overrides.json").read_text(encoding="utf-8"))["毒蘑菇|周笔畅"]
            self.assertEqual((override["videoId"], override["release_date"]), ("NEWNEWNEW01", "2006-08-12"))
            self.assertIn("2026-10-27 paperbridge", override["reason"])
            cache = json.loads((root / "cache.json").read_text(encoding="utf-8"))["毒蘑菇|周笔畅"]
            self.assertEqual(cache["yt"]["videoId"], "NEWNEWNEW01")
            cands = json.loads((root / "cands.json").read_text(encoding="utf-8"))["昨日重现"]["毒蘑菇|周笔畅"]
            self.assertEqual(cands["current"]["label"], "原唱录音室")
            self.assertEqual(cands["candidates"][0]["video_id"], "OLDOLDOLD01")


    def test_follows_moves_deletes_adds_and_date_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fields = ["title", "artists", "album", "release_date", "videoId", "source", "note"]

            def write(name: str, rows: list) -> None:
                with (root / name).open("w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader()
                    for r in rows:
                        w.writerow({k: r.get(k, "") for k in fields})

            write("ny.csv", [
                {"title": "半面妆", "artists": "爱乐团王超", "album": "专辑A", "release_date": "2006-11-01", "videoId": "BANMIANZHU1", "source": "qq"},
                {"title": "滴答", "artists": "侃侃", "release_date": "2024", "videoId": "DIDADIDADI1", "source": "qq"},
            ])
            write("zr.csv", [{"title": "红豆", "artists": "王菲", "release_date": "1998-01-01", "videoId": "HONGDOU0001", "source": "qq"}])
            (root / "playlists.json").write_text(json.dumps([
                {"title": "not yet", "id": "PL1", "path": "ny.csv"}, {"title": "昨日重现", "id": "PL2", "path": "zr.csv"},
                {"title": "其它", "id": "PL3", "path": "."},
            ]), encoding="utf-8")
            (root / "overrides.json").write_text("{}", encoding="utf-8")
            (root / "cache.json").write_text("{}", encoding="utf-8")
            library = {"playlists": [
                {"name": "not yet", "tracks": []},  # 半面妆搬去昨日重现，滴答删了
                {"name": "昨日重现", "tracks": [
                    {"key": "红豆|王菲", "title": "红豆", "artists": "王菲", "release_date": "1998-01-01", "video_id": "HONGDOU0001"},
                    {"key": "半面妆|爱乐团王超", "title": "半面妆", "artists": "爱乐团王超", "release_date": "2006-11-01",
                     "video_id": "BANMIANZHU1"},
                    {"key": "今生你作伴|陈慧琳", "title": "今生你作伴", "artists": "陈慧琳", "release_date": "1998-06",
                     "video_id": "JINSHENG001", "current": {"video_id": "JINSHENG001", "label": "官方音轨", "kind": "original_studio"}},
                ]},
                {"name": "没有本地 CSV", "tracks": []},
            ]}
            kwargs = dict(playlists_json=root / "playlists.json", repo_root=root, overrides_path=root / "overrides.json",
                          cache_path=root / "cache.json", candidates_path=root / "cands.json",
                          removed_path=root / "removed.json", today=date(2026, 11, 11))

            preview = import_library(library, dry_run=True, **kwargs)
            self.assertIn("滴答", (root / "ny.csv").read_text(encoding="utf-8"))
            self.assertFalse((root / "removed.json").exists())

            result = import_library(library, **kwargs)
            self.assertEqual(preview["membership"], result["membership"])
            ops = sorted((m["op"], m["key"]) for m in result["membership"])
            self.assertEqual(ops, [("add", "今生你作伴|陈慧琳"), ("move_in", "半面妆|爱乐团王超"),
                                   ("move_out", "半面妆|爱乐团王超"), ("remove", "滴答|侃侃")])
            self.assertEqual(result["unmatched"], ["没有本地 CSV: 本地没有对应 CSV"])
            self.assertEqual(list(csv.DictReader((root / "ny.csv").open(encoding="utf-8"))), [])
            zr = list(csv.DictReader((root / "zr.csv").open(encoding="utf-8")))
            # 按日期从旧到新；搬来的歌保留原来的列，网页加的歌标来源。
            self.assertEqual([r["title"] for r in zr], ["红豆", "今生你作伴", "半面妆"])
            self.assertEqual(zr[2]["album"], "专辑A")
            self.assertEqual((zr[1]["source"], zr[1]["videoId"], zr[1]["release_date"]), ("paperbridge", "JINSHENG001", "1998-06"))
            overrides = json.loads((root / "overrides.json").read_text(encoding="utf-8"))
            self.assertEqual(overrides["今生你作伴|陈慧琳"]["videoId"], "JINSHENG001")
            self.assertEqual(overrides["今生你作伴|陈慧琳"]["release_date"], "1998-06")
            removed = json.loads((root / "removed.json").read_text(encoding="utf-8"))
            self.assertEqual(removed, [{"playlist": "not yet", "key": "滴答|侃侃", "at": "2026-11-11"}])

            # 改日期：CSV 和 override 都跟着改，再次拉回不再有改动。
            library["playlists"][1]["tracks"][0]["release_date"] = "1998-03-01"
            result = import_library(library, **kwargs)
            self.assertEqual(result["membership"], [{"op": "date", "playlist": "昨日重现", "key": "红豆|王菲",
                                                     "from": "1998-01-01", "to": "1998-03-01"}])
            self.assertEqual(json.loads((root / "overrides.json").read_text(encoding="utf-8"))["红豆|王菲"]["release_date"], "1998-03-01")
            again = import_library(library, **kwargs)
            self.assertEqual((again["changes"], again["membership"]), ([], []))


if __name__ == "__main__":
    unittest.main()
