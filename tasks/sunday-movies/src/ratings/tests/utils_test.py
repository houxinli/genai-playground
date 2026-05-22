import unittest

from ratings.utils import clean_search_title, extract_title_year


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


if __name__ == "__main__":
    unittest.main()
