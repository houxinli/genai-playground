"""Utilities to fetch movie ratings from multiple providers."""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

try:  # pragma: no cover - support direct execution
    from .base import RatingFetcher, RatingResult
except ImportError:  # pragma: no cover
    from base import RatingFetcher, RatingResult  # type: ignore


logger = logging.getLogger(__name__)


class RatingsAggregator:
    """Helper that queries a list of providers and aggregates results."""

    def __init__(self, fetchers: Iterable[RatingFetcher]) -> None:
        self.fetchers: List[RatingFetcher] = list(fetchers)

    def fetch(self, title: str, *, year: Optional[int] = None) -> List[RatingResult]:
        results: List[RatingResult] = []
        for fetcher in self.fetchers:
            try:
                result = fetcher.fetch(title, year=year)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.debug("rating fetch failed", extra={"source": fetcher.source, "title": title}, exc_info=exc)
                continue
            if result is None:
                continue
            results.append(result)
        # Sort higher confidence and score first
        results.sort(key=lambda r: (r.confidence, r.score / r.scale if r.scale else 0), reverse=True)
        return results
