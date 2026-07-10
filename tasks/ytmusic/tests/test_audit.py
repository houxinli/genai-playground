import unittest

from tasks.ytmusic.src.ytmusic.audit import (
    audit_playlist,
    bad_hits,
    load_aliases,
    pick_video,
    title_match,
)


class BadHitsTest(unittest.TestCase):
    def test_live_and_medley(self) -> None:
        self.assertIn("live", bad_hits("夜夜夜夜 (Live)", "夜夜夜夜"))
        self.assertIn("medley_title", bad_hits("流沙+天天", "流沙"))
        # 期望标题本身含关键词时不算
        self.assertEqual(bad_hits("Last Dance", "Last Dance"), [])
        # 括号里的年份不触发串烧判定
        self.assertNotIn("medley_title", bad_hits("AMANI (Live in Hong Kong / 1991)", "Amani")[1:])


class TitleMatchTest(unittest.TestCase):
    def test_traditional_and_suffix(self) -> None:
        self.assertTrue(title_match("听海", "聽海"))
        self.assertTrue(title_match("爱你", "愛你 - Ai Ni"))
        self.assertFalse(title_match("红豆", "但願人長久"))


class PickVideoTest(unittest.TestCase):
    def test_alias_and_duration_pick_original(self) -> None:
        candidates = [
            {"videoId": "live1", "title": "愛你 (Live)", "artists": [{"name": "Cyndi Wang"}], "duration_seconds": 219},
            {"videoId": "orig", "title": "愛你 - Ai Ni", "artists": [{"name": "Cyndi Wang"}], "duration_seconds": 220},
            {"videoId": "cover", "title": "爱你", "artists": [{"name": "某翻唱"}], "duration_seconds": 219},
        ]
        best = pick_video(lambda q: candidates, "爱你", "王心凌", qq_len=219, aliases=load_aliases())
        self.assertIsNotNone(best)
        self.assertEqual(best["videoId"], "orig")

    def test_no_confident_match_returns_none(self) -> None:
        candidates = [
            {"videoId": "x", "title": "别的歌", "artists": [{"name": "路人"}], "duration_seconds": 100},
        ]
        self.assertIsNone(pick_video(lambda q: candidates, "爱你", "王心凌", qq_len=219, aliases={}))


class AuditPlaylistTest(unittest.TestCase):
    def test_flags(self) -> None:
        rows = [
            {"title": "雾里看花", "artists": "那英", "videoId": "v1"},
            {"title": "旋木", "artists": "王菲", "videoId": "v2"},
            {"title": "没视频", "artists": "某人", "videoId": ""},
        ]
        infos = {
            "v1": {"actual_title": "雾里看花 (Live)", "author": "Na Ying", "length": 139, "status": "OK"},
            "v2": {"actual_title": "棋子", "author": "王菲", "length": 287, "status": "UNPLAYABLE"},
        }
        report = audit_playlist(rows, lambda v: infos.get(v), {"雾里看花|那英": 242})
        self.assertTrue(any(f.startswith("bad_keyword") for f in report[0]["flags"]))
        self.assertTrue(any(f.startswith("duration_gap") for f in report[0]["flags"]))
        # 英文艺名靠对照表匹配,不应误报
        self.assertNotIn("artist_mismatch", report[0]["flags"])
        self.assertIn("title_mismatch", report[1]["flags"])
        self.assertTrue(any(f.startswith("unavailable") for f in report[1]["flags"]))
        self.assertEqual(report[2]["flags"], ["no_videoId"])


if __name__ == "__main__":
    unittest.main()
