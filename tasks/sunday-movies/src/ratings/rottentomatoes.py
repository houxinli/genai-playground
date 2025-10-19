"""Rotten Tomatoes rating fetcher."""

from __future__ import annotations

from typing import Optional

import requests

from .base import RatingFetcher, RatingResult
from .utils import pick_best_candidate


class RottenTomatoesFetcher(RatingFetcher):
    source = "rottentomatoes"

    SEARCH_URL = "https://www.rottentomatoes.com/napi/search/"
    MOVIE_URL_TEMPLATE = "https://www.rottentomatoes.com{path}"

    def __init__(self, *, timeout: int = 15) -> None:
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://www.rottentomatoes.com/",
            }
        )

    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        resp = self.session.get(self.SEARCH_URL, params={"query": title}, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        movies = payload.get("movies") or []
        candidate = pick_best_candidate(movies, title=title, year=year)
        if not candidate:
            return None
        path = candidate.get("url") or candidate.get("path")
        if not path:
            return None

        detail_url = self.MOVIE_URL_TEMPLATE.format(path=path)
        api_url = detail_url.replace("https://www.rottentomatoes.com", "https://www.rottentomatoes.com/napi/movie")
        resp = self.session.get(api_url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        scoreboard = data.get("scoreboard") or {}

        critics_score = scoreboard.get("tomatometerScore", {}).get("value")
        audience_score = scoreboard.get("audienceScore", {}).get("value")

        if critics_score is None and audience_score is None:
            return None

        score = float(critics_score if critics_score is not None else audience_score)
        summary = None
        if critics_score is not None and audience_score is not None:
            summary = f"Critics {critics_score}%, Audience {audience_score}%"
        elif critics_score is not None:
            summary = f"Critics {critics_score}%"
        elif audience_score is not None:
            summary = f"Audience {audience_score}%"

        return RatingResult(
            source=self.source,
            score=score,
            scale=100.0,
            url=detail_url,
            summary=summary,
            confidence=0.6,
        )

