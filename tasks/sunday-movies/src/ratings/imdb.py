"""IMDb rating fetcher."""

from __future__ import annotations

import json
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import RatingFetcher, RatingResult
from .utils import normalize_title, pick_best_candidate


class ImdbFetcher(RatingFetcher):
    source = "imdb"

    SUGGEST_URL_TEMPLATE = "https://v2.sg.media-imdb.com/suggestion/{first}/{query}.json"

    def __init__(self, *, timeout: int = 15) -> None:
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        enc = requests.utils.quote(title)
        url = self.SUGGEST_URL_TEMPLATE.format(first=title[0].lower(), query=enc)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        payload = json.loads(resp.text)
        candidates = payload.get("d") or []
        candidate = pick_best_candidate(candidates, title=title, year=year)
        if not candidate:
            return None
        imdb_id = candidate.get("id") or candidate.get("const")
        if not imdb_id:
            return None

        detail_url = f"https://www.imdb.com/title/{imdb_id}/"
        html = self.session.get(detail_url, timeout=self.timeout)
        html.raise_for_status()
        soup = BeautifulSoup(html.text, "html.parser")

        rating_value = None
        vote_summary = None

        ld_json_tag = soup.find("script", type="application/ld+json")
        if ld_json_tag and ld_json_tag.text:
            try:
                data = json.loads(ld_json_tag.text)
                agg = data.get("aggregateRating") if isinstance(data, dict) else None
                if agg:
                    rating_value = agg.get("ratingValue")
                    vote_summary = agg.get("ratingCount")
            except json.JSONDecodeError:
                pass

        if rating_value is None:
            meta_tag = soup.find("span", attrs={"class": "sc-bde20123-1"})
            if meta_tag and meta_tag.text:
                rating_value = meta_tag.text.strip()

        if rating_value is None:
            return None

        try:
            score = float(str(rating_value))
        except ValueError:
            return None

        summary = None
        if vote_summary:
            summary = f"{vote_summary} ratings"

        return RatingResult(
            source=self.source,
            score=score,
            scale=10.0,
            url=detail_url,
            summary=summary,
            confidence=0.7,
        )

