"""Douban rating fetcher."""

from __future__ import annotations

import json
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import RatingFetcher, RatingResult
from .utils import pick_best_candidate


class DoubanFetcher(RatingFetcher):
    source = "douban"

    SUGGEST_URL = "https://movie.douban.com/j/subject_suggest"

    def __init__(self, *, timeout: int = 15) -> None:
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Referer": "https://movie.douban.com/",
            }
        )

    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        params = {"q": title}
        resp = self.session.get(self.SUGGEST_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        suggestions = json.loads(resp.text)
        candidate = pick_best_candidate(suggestions, title=title, year=year)
        if not candidate:
            return None
        subject_id = candidate.get("id")
        if not subject_id:
            return None

        detail_url = f"https://movie.douban.com/subject/{subject_id}/"
        html = self.session.get(detail_url, timeout=self.timeout)
        html.raise_for_status()
        soup = BeautifulSoup(html.text, "html.parser")

        rating_tag = soup.select_one("strong.ll.rating_num") or soup.select_one("span[property='v:average']")
        count_tag = soup.select_one("span[property='v:votes']")
        if not rating_tag or not rating_tag.text.strip():
            return None

        try:
            score = float(rating_tag.text.strip())
        except ValueError:
            return None

        summary = None
        if count_tag and count_tag.text.strip():
            summary = f"{count_tag.text.strip()} votes"

        return RatingResult(
            source=self.source,
            score=score,
            scale=10.0,
            url=detail_url,
            summary=summary,
            confidence=0.7,
        )

