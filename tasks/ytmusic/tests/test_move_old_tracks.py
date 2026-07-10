import csv
import tempfile
import unittest
from pathlib import Path

from tasks.ytmusic.src.core.move_old_tracks import compute_cutoff_date, move_old_tracks
from tasks.ytmusic.src.core.normalize import is_foreign

FIELDS = ["title", "artists", "release_date", "videoId"]


def write(path: Path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read(path: Path):
    return list(csv.DictReader(path.open()))


class IsForeignTest(unittest.TestCase):
    def test_chinese(self) -> None:
        self.assertFalse(is_foreign("童话", "光良"))
        self.assertFalse(is_foreign("Kiss Goodbye", "王力宏"))
        self.assertFalse(is_foreign("不要在我寂寞的时候说爱我", "T.R.Y"))

    def test_foreign(self) -> None:
        self.assertTrue(is_foreign("Because of You", "Kelly Clarkson"))
        self.assertTrue(is_foreign("오나라 I", "지현"))
        self.assertTrue(is_foreign("PLANET", "Lambsey (ラムジ)"))
        # 日语歌名纯汉字,靠艺人名里的假名识别
        self.assertTrue(is_foreign("空", "大黒摩季 (おおぐろ まき)"))


class CutoffDateTest(unittest.TestCase):
    def test_now_year_keeps_year_semantics(self) -> None:
        self.assertEqual(compute_cutoff_date(20, now_year=2025), "2005-12-31")

    def test_day_precision(self) -> None:
        from datetime import date

        self.assertEqual(compute_cutoff_date(20, today=date(2026, 7, 10)), "2006-07-10")
        self.assertEqual(compute_cutoff_date(20, today=date(2024, 2, 29)), "2004-02-29")
        # 目标年不是闰年时 2月29日 回退到 28日
        self.assertEqual(compute_cutoff_date(21, today=date(2024, 2, 29)), "2003-02-28")


class MoveOldTracksSplitTest(unittest.TestCase):
    def test_split_by_language_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "not_yet.csv"
            tgt = Path(tmp) / "zh.csv"
            foreign = Path(tmp) / "foreign.csv"
            write(src, [
                {"title": "老中文歌", "artists": "某歌手", "release_date": "2005-01-01", "videoId": "a"},
                {"title": "Old Song", "artists": "Someone", "release_date": "2004-01-01", "videoId": "b"},
                {"title": "新歌", "artists": "某歌手", "release_date": "2010-01-01", "videoId": "c"},
                {"title": "无日期", "artists": "某歌手", "release_date": "", "videoId": "d"},
            ])
            write(tgt, [{"title": "已有", "artists": "某歌手", "release_date": "1999-01-01", "videoId": "e"}])

            summary = move_old_tracks(
                src, tgt, older_than=20, now_year=2025, foreign_target_csv=foreign,
            )
            self.assertEqual(summary["moved_cn"], 1)
            self.assertEqual(summary["moved_foreign"], 1)
            self.assertEqual({r["title"] for r in read(src)}, {"新歌", "无日期"})
            self.assertEqual({r["title"] for r in read(tgt)}, {"已有", "老中文歌"})
            self.assertEqual({r["title"] for r in read(foreign)}, {"Old Song"})

    def test_dedupe_against_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "s.csv"
            tgt = Path(tmp) / "t.csv"
            write(src, [{"title": "重复", "artists": "A", "release_date": "2000-01-01", "videoId": "x"}])
            write(tgt, [{"title": "重复", "artists": "A", "release_date": "2000-01-01", "videoId": "y"}])
            summary = move_old_tracks(src, tgt, older_than=20, now_year=2025)
            self.assertEqual(summary["source_count"], 0)
            self.assertEqual(summary["target_count"], 1)


if __name__ == "__main__":
    unittest.main()
