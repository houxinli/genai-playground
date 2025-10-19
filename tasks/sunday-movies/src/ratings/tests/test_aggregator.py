"""Tests for rating aggregator utility."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_FILE = Path(__file__).resolve()
RATINGS_ROOT = _FILE.parents[1]
if str(RATINGS_ROOT) not in sys.path:
    sys.path.insert(0, str(RATINGS_ROOT))

from aggregator import RatingsAggregator
from base import RatingFetcher, RatingResult


class StubFetcher(RatingFetcher):
    def __init__(self, source: str, score: float, *, confidence: float = 0.5) -> None:
        super().__init__(timeout=1)
        self.source = source
        self._score = score
        self._confidence = confidence

    def fetch(self, title: str, *, year: int | None = None) -> RatingResult:
        return RatingResult(
            source=self.source,
            score=self._score,
            scale=10.0,
            url="https://example.com",
            confidence=self._confidence,
        )


class RatingsAggregatorTests(unittest.TestCase):
    def test_returns_sorted_results(self) -> None:
        agg = RatingsAggregator(
            [
                StubFetcher("low", 6.0, confidence=0.2),
                StubFetcher("high", 8.5, confidence=0.8),
            ]
        )
        results = agg.fetch("Any Title", year=2025)
        self.assertEqual([r.source for r in results], ["high", "low"])


if __name__ == "__main__":
    unittest.main()
