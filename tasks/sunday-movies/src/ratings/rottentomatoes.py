"""Rotten Tomatoes rating fetcher via HTML parsing (search + scorecard)."""

from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:  # pragma: no cover - allow running without package context
    from .base import RatingFetcher, RatingResult
    from .utils import pick_best_candidate
except ImportError:  # pragma: no cover
    from base import RatingFetcher, RatingResult  # type: ignore
    from utils import pick_best_candidate  # type: ignore


class RottenTomatoesFetcher(RatingFetcher):
    """Fetch critic/audience scores from RottenTomatoes search + detail pages."""

    source = "rottentomatoes"
    BASE_URL = "https://www.rottentomatoes.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(self, *, timeout: int = 15) -> None:
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.rottentomatoes.com/",
            }
        )

    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        candidates = self._search_movies(title)
        if not candidates:
            return None

        candidate = pick_best_candidate(candidates, title=title, year=year)
        if not candidate:
            return None

        detail = self._parse_detail(candidate["url"])

        critics_score = detail.get("critics_score")
        audience_score = detail.get("audience_score")
        summary_parts = []
        if critics_score is not None:
            summary_parts.append(f"Critics {critics_score:.0f}%")
        if audience_score is not None:
            summary_parts.append(f"Audience {audience_score:.0f}%")

        if critics_score is None and audience_score is None:
            # Fall back to search-page tomatometer if the detail hero is missing scores.
            fallback = candidate.get("search_score")
            if fallback is None:
                return None
            critics_score = float(fallback)
            summary_parts.append(f"Search Tomatometer {critics_score:.0f}%")

        selected_score = critics_score if critics_score is not None else audience_score
        converted_score = None
        if selected_score is not None:
            converted_score = (selected_score / 100.0) * 10.0

        confidence = 0.55
        available_sources = sum(
            1 for score in (critics_score, audience_score) if score is not None
        )
        if available_sources == 2:
            confidence += 0.2
        elif available_sources == 1:
            confidence += 0.1
        if detail.get("critics_reviews") or detail.get("audience_ratings"):
            confidence += 0.05
        confidence = min(confidence, 0.95)

        if converted_score is None:
            return None

        metadata = {
            "critics_score": critics_score,
            "audience_score": audience_score,
        }

        result = RatingResult(
            source=self.source,
            score=converted_score,
            scale=10.0,
            url=detail.get("url", candidate["url"]),
            summary=" | ".join(summary_parts) if summary_parts else "Rotten Tomatoes",
            confidence=confidence,
            metadata=metadata,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _search_movies(self, title: str) -> List[Dict]:
        """Parse the public search page for movie matches."""
        resp = self.session.get(self.SEARCH_URL, params={"search": title}, timeout=self.timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("search-page-media-row")
        results: List[Dict] = []

        for row in rows:
            anchor = row.find("a", attrs={"slot": "title"})
            if not anchor:
                continue

            movie_title = anchor.get_text(strip=True)
            href = anchor.get("href")
            if not movie_title or not href:
                continue

            full_url = href if href.startswith("http") else urljoin(self.BASE_URL, href)
            release_year = self._safe_int(row.get("release-year"))
            score = self._safe_int(row.get("tomatometer-score"))

            results.append(
                {
                    "title": movie_title,
                    "url": full_url,
                    "year": release_year,
                    "search_score": score,
                }
            )

        return results

    def _parse_detail(self, url: str) -> Dict[str, Optional[float]]:
        """Parse the movie detail page for critic/audience scores."""
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        critics_score = self._extract_score(soup, "criticsScore")
        audience_score = self._extract_score(soup, "audienceScore")

        critics_reviews = self._extract_link_text(soup, "criticsReviews")
        audience_ratings = self._extract_link_text(soup, "audienceReviews") or self._extract_link_text(
            soup, "audienceRatings"
        )

        return {
            "url": url,
            "critics_score": critics_score,
            "audience_score": audience_score,
            "critics_reviews": critics_reviews,
            "audience_ratings": audience_ratings,
        }

    @staticmethod
    def _extract_score(soup: BeautifulSoup, slot_name: str) -> Optional[float]:
        node = soup.find("rt-text", attrs={"slot": slot_name})
        if not node:
            return None
        text = node.get_text(strip=True)
        if not text or text in {"--", "N/A"}:
            return None
        text = text.replace("%", "")
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _extract_link_text(soup: BeautifulSoup, slot_name: str) -> Optional[str]:
        node = soup.find("rt-link", attrs={"slot": slot_name})
        if node:
            text = node.get_text(strip=True)
            if text:
                return text
        return None

    @staticmethod
    def _safe_int(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
