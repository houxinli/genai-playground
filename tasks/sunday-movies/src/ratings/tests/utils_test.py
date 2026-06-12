import unittest

from ratings.utils import rating_cache_key, clean_search_title, extract_title_year


class CleanSearchTitleTest(unittest.TestCase):
    def test_strips_trailing_year(self):
        self.assertEqual(clean_search_title("Chand Mera Dil (2026)"), "Chand Mera Dil")

    def test_strips_anniversary(self):
        self.assertEqual(clean_search_title("Legally Blonde 25th Anniversary"), "Legally Blonde")

    def test_strips_format_tags(self):
        self.assertEqual(clean_search_title("Avatar RealD 3D"), "Avatar")
        self.assertEqual(clean_search_title("Dune IMAX"), "Dune")

    def test_falls_back_when_all_noise(self):
        # mostly-noise concert listing should not collapse to empty
        out = clean_search_title("(2026)")
        self.assertTrue(out)

    def test_plain_title_unchanged(self):
        self.assertEqual(clean_search_title("Dune: Part Two"), "Dune: Part Two")


class ExtractTitleYearTest(unittest.TestCase):
    def test_parenthesized_year(self):
        self.assertEqual(extract_title_year("Corporate Retreat (2026)"), 2026)

    def test_trailing_bare_year(self):
        self.assertEqual(extract_title_year("Some Concert 2026"), 2026)

    def test_no_year(self):
        self.assertIsNone(extract_title_year("Vanishing Point"))

    def test_ignores_midstring_number(self):
        self.assertIsNone(extract_title_year("Ocean's 11"))


class TrailingNoiseAndCacheKeyTest(unittest.TestCase):
    def test_embedded_noise_words_are_preserved(self):
        # review PR #3:未锚定的噪声词会破坏正经标题
        self.assertEqual(clean_search_title("Prime Target"), "Prime Target")
        self.assertEqual(clean_search_title("Encore Week"), "Encore Week")

    def test_trailing_format_chain_is_stripped(self):
        self.assertEqual(clean_search_title("Dune: Part Two IMAX 3D"), "Dune: Part Two")
        self.assertEqual(clean_search_title("Up (2009) RealD 3D"), "Up")

    def test_mostly_noise_title_falls_back(self):
        self.assertEqual(clean_search_title("Encore!"), "Encore!")

    def test_cache_key_distinguishes_years(self):
        old = rating_cache_key("Nosferatu", 1922)
        new = rating_cache_key("Nosferatu", 2024)
        self.assertNotEqual(old, new)
        # 同年不同格式后缀共享(清洗后标题相同)
        self.assertEqual(
            rating_cache_key(clean_search_title("Nosferatu IMAX"), 2024),
            rating_cache_key(clean_search_title("Nosferatu"), 2024),
        )


if __name__ == "__main__":
    unittest.main()
