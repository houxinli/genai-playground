"""Tests for RottenTomatoesFetcher (HTML parsing helpers)."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

import requests
from pathlib import Path

_FILE = Path(__file__).resolve()
RATINGS_ROOT = _FILE.parents[1]
if str(RATINGS_ROOT) not in sys.path:
    sys.path.insert(0, str(RATINGS_ROOT))

from rottentomatoes import RottenTomatoesFetcher


SEARCH_HTML = """
<html>
  <body>
    <search-page-media-row release-year="2025" tomatometer-score="54">
      <a slot="title" href="https://www.rottentomatoes.com/m/tron_ares">TRON: Ares</a>
    </search-page-media-row>
    <search-page-media-row release-year="2010" tomatometer-score="51">
      <a slot="title" href="https://www.rottentomatoes.com/m/tron_legacy">Tron: Legacy</a>
    </search-page-media-row>
  </body>
</html>
""".strip()


DETAIL_HTML = """
<html>
  <body>
    <media-scorecard>
      <rt-text slot="criticsScore">54%</rt-text>
      <rt-text slot="audienceScore">85%</rt-text>
      <rt-link slot="criticsReviews">257 Reviews</rt-link>
      <rt-link slot="audienceReviews">10000+ Verified Ratings</rt-link>
    </media-scorecard>
  </body>
</html>
""".strip()


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class RottenTomatoesFetcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = RottenTomatoesFetcher()

    def test_fetch_returns_rating_with_critics_and_audience(self) -> None:
        call_responses = [DummyResponse(SEARCH_HTML), DummyResponse(DETAIL_HTML)]

        def fake_get(*_, **__):
            return call_responses.pop(0)

        with patch.object(requests.Session, "get", side_effect=fake_get):
            result = self.fetcher.fetch("Tron: Ares", year=2025)

        self.assertIsNotNone(result)
        assert result  # for type checker
        self.assertEqual(result.score, 54.0)
        self.assertIn("Critics 54%", result.summary)
        self.assertIn("Audience 85%", result.summary)

    def test_fetch_returns_none_when_no_candidates(self) -> None:
        empty_html = "<html><body></body></html>"
        call_responses = [DummyResponse(empty_html)]

        def fake_get(*_, **__):
            return call_responses.pop(0)

        with patch.object(requests.Session, "get", side_effect=fake_get):
            result = self.fetcher.fetch("Unknown Movie", year=1999)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
