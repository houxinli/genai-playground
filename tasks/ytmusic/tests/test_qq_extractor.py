import unittest
from pathlib import Path

from tasks.ytmusic.src.qqmusic.qq_extractor import extract_from_csv


FIXTURE = Path(__file__).parent / "data" / "qq_sample.csv"


class QQExtractorTest(unittest.TestCase):
    def test_extract_and_dedupe(self) -> None:
        songs = extract_from_csv(FIXTURE, dedupe=True)
        # 输入 3 行，1 行重复；应只返回 2 首
        self.assertEqual(len(songs), 2)
        titles = {s["title"] for s in songs}
        self.assertIn("晴天", titles)
        self.assertIn("领悟", titles)
        for song in songs:
            self.assertEqual(song["source"], "qq")
            self.assertIn("title", song)
            self.assertIn("artists", song)


if __name__ == "__main__":
    unittest.main()
