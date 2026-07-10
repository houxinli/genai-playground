import unittest

from tasks.ytmusic.src.qqmusic.qq_playlist_fetcher import parse_playlist


class ParsePlaylistTest(unittest.TestCase):
    def test_parse_and_normalize(self) -> None:
        raw = {
            "cdlist": [{
                "dissname": "昨日重现",
                "songlist": [
                    {
                        "songname": "晴天 (Live)",
                        "singer": [{"name": "周杰伦"}, {"name": "某和声"}],
                        "albumname": "叶惠美",
                        "albummid": "am1",
                        "songmid": "sm1",
                        "songid": 123,
                        "interval": 269,
                    },
                ],
            }],
        }
        parsed = parse_playlist(raw)
        self.assertEqual(parsed["name"], "昨日重现")
        song = parsed["songs"][0]
        # 与 qq_extractor 相同的规范化:去版本后缀、只取第一艺人
        self.assertEqual(song["title"], "晴天")
        self.assertEqual(song["artists"], "周杰伦")
        self.assertEqual(song["song_mid"], "sm1")
        self.assertEqual(song["interval_seconds"], "269")

    def test_empty(self) -> None:
        self.assertEqual(parse_playlist({})["songs"], [])


if __name__ == "__main__":
    unittest.main()
