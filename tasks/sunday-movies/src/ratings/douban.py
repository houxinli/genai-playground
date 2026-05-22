"""Douban rating fetcher.

Primary path uses the Douban "Frodo" mini-program search API, which accepts an
English query and returns the matching Chinese subject (title, year, rating,
votes, subject id) in a single request. This is far more reliable than scraping
the public HTML search page, which is heavily anti-scraped and indexed mostly by
Chinese titles. The legacy HTML scraper is kept as a fallback.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import RatingFetcher, RatingResult
from .utils import normalize_title, title_similarity


class DoubanFetcher(RatingFetcher):
    source = "douban"

    # Frodo (mini-program) API — public client key, accepts English queries.
    FRODO_SEARCH_URL = "https://frodo.douban.com/api/v2/search/movie"
    FRODO_APIKEY = "0ac44ae016490db2204ce0a042db2916"
    FRODO_HEADERS = {
        "User-Agent": "MicroMessenger/",
        "Referer": "https://servicewechat.com/wx2f9b06c1de1ccfca/91/page-frame.html",
    }

    # Legacy HTML search (fallback only).
    SEARCH_URL = "https://www.douban.com/search"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self, *, timeout: int = 15, delay: float = 1.0) -> None:
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.delay = delay

    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        """Fetch a Douban rating for the given (English) title."""
        try:
            result = self._fetch_via_frodo(title, year=year)
            if result is not None:
                return result
        except Exception as e:  # noqa: BLE001 - fall back to HTML on any Frodo error
            print(f"Frodo lookup failed for '{title}', falling back to HTML: {e}")

        try:
            return self._fetch_via_html(title, year=year)
        except Exception as e:  # noqa: BLE001
            print(f"Error fetching Douban rating for '{title}': {e}")
            return None

    # ------------------------------------------------------------------ Frodo

    def _fetch_via_frodo(self, title: str, *, year: Optional[int]) -> Optional[RatingResult]:
        params = {"q": title, "count": 5, "apikey": self.FRODO_APIKEY}
        resp = requests.get(
            self.FRODO_SEARCH_URL,
            params=params,
            headers=self.FRODO_HEADERS,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        if self.delay > 0:
            time.sleep(self.delay)

        items = resp.json().get("items") or []
        candidates = []
        for item in items:
            if item.get("layout") != "subject":
                continue
            target = item.get("target") or {}
            subject_id = target.get("id")
            if not subject_id:
                continue
            rating = target.get("rating") or {}
            cand_year = target.get("year")
            try:
                cand_year = int(cand_year) if cand_year is not None else None
            except (TypeError, ValueError):
                cand_year = None
            candidates.append(
                {
                    "id": str(subject_id),
                    "title": target.get("title"),
                    "year": cand_year,
                    "score": float(rating.get("value") or 0.0),
                    "votes": int(rating.get("count") or 0),
                    "card_subtitle": target.get("card_subtitle") or "",
                }
            )

        chosen = self._select_frodo_candidate(candidates, year)
        if not chosen:
            return None

        return self._build_frodo_result(chosen)

    def _select_frodo_candidate(self, candidates: list, year: Optional[int]) -> Optional[dict]:
        """Pick the best Frodo candidate.

        Items arrive relevance-ranked. When a year is known, prefer a candidate
        within ±1 year (re-releases / anniversaries match their original year);
        otherwise keep Douban's top relevance hit. Candidates with a real rating
        win over rating-less entries at the same relevance.
        """
        if not candidates:
            return None

        if year is not None:
            close = [c for c in candidates if c["year"] is not None and abs(c["year"] - year) <= 1]
            rated_close = [c for c in close if c["score"] > 0]
            if rated_close:
                return rated_close[0]
            if close:
                return close[0]

        rated = [c for c in candidates if c["score"] > 0]
        if rated:
            return rated[0]
        return candidates[0]

    def _build_frodo_result(self, cand: dict) -> RatingResult:
        url = f"https://movie.douban.com/subject/{cand['id']}/"
        local_title = cand.get("title")
        director = self._director_from_card(cand.get("card_subtitle", ""))

        summary_parts = []
        if local_title:
            summary_parts.append(local_title)
        if cand["score"] > 0 and cand["votes"]:
            summary_parts.append(f"{cand['votes']} 人评价")
        elif cand["score"] <= 0:
            summary_parts.append("豆瓣暂无评分")
        if director:
            summary_parts.append(f"导演: {director}")
        if cand.get("year"):
            summary_parts.append(f"年份: {cand['year']}")

        has_rating = cand["score"] > 0
        return RatingResult(
            source=self.source,
            score=cand["score"],
            scale=10.0,
            url=url,
            summary=" | ".join(summary_parts) if summary_parts else "豆瓣",
            # confidence 0 keeps unrated entries out of the aggregate while still
            # surfacing the matched Chinese title.
            confidence=0.9 if has_rating else 0.0,
            local_title=local_title,
            metadata={"no_rating": not has_rating, "votes": cand["votes"]},
        )

    @staticmethod
    def _director_from_card(card_subtitle: str) -> Optional[str]:
        # card_subtitle: "国家 / 类型 / 导演 / 主演"
        parts = [p.strip() for p in card_subtitle.split("/") if p.strip()]
        if len(parts) >= 4:
            return parts[2]
        if len(parts) == 3:
            return parts[2]
        return None

    # ------------------------------------------------------------------- HTML

    def _fetch_via_html(self, title: str, *, year: Optional[int]) -> Optional[RatingResult]:
        search_results = self._search_movies(title)
        if not search_results:
            return None
        best_match = self._select_best_match(search_results, title, year)
        if not best_match:
            return None
        details = self._get_movie_details(best_match["url"])
        return self._build_rating_result(details, best_match)

    def _search_movies(self, title: str) -> list:
        """Search for movies on Douban (legacy HTML path)."""
        params = {"cat": "1002", "q": title}
        try:
            response = self.session.get(self.SEARCH_URL, params=params, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            movies = []
            for item in soup.find_all("div", class_="result")[:5]:
                try:
                    title_link = item.find("div", class_="title")
                    if not title_link:
                        continue
                    link = title_link.find("a")
                    if not link:
                        continue
                    rating_span = item.find("span", class_="rating_nums")
                    info_div = item.find("div", class_="info")
                    movies.append(
                        {
                            "title": link.get_text(strip=True),
                            "rating": rating_span.get_text(strip=True) if rating_span else None,
                            "url": link.get("href", ""),
                            "info": info_div.get_text(strip=True) if info_div else "",
                        }
                    )
                except Exception:
                    continue

            if self.delay > 0:
                time.sleep(self.delay)
            return movies
        except Exception as e:
            print(f"Error searching movies: {e}")
            return []

    def _select_best_match(self, movies: list, original_title: str, year: Optional[int]) -> Optional[dict]:
        if not movies:
            return None
        if len(movies) == 1:
            return movies[0]

        best_match = None
        best_score = 0.0
        normalized_original = normalize_title(original_title)
        for movie in movies:
            similarity = title_similarity(normalized_original, normalize_title(movie["title"]))
            if year and self._extract_year_from_info(movie["info"]) == year:
                similarity += 0.2
            if similarity > best_score and similarity > 0.3:
                best_score = similarity
                best_match = movie
        return best_match

    def _get_movie_details(self, movie_url: str) -> Optional[dict]:
        try:
            if "douban.com/link2/" in movie_url:
                subject_id = self._extract_subject_id_from_url(movie_url)
                if subject_id:
                    movie_url = f"https://movie.douban.com/subject/{subject_id}/"

            response = self.session.get(movie_url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            details: dict = {}
            title_elem = soup.find("span", property="v:itemreviewed")
            if title_elem:
                details["title"] = title_elem.get_text(strip=True)

            rating = None
            for selector in ("strong.ll.rating_num", 'span[property="v:average"]', ".rating_num", ".ll.rating_num"):
                rating_elem = soup.select_one(selector)
                if rating_elem:
                    try:
                        rating = float(rating_elem.get_text(strip=True))
                        break
                    except ValueError:
                        continue
            if rating:
                details["rating"] = rating

            votes_span = soup.find("span", property="v:votes")
            if votes_span:
                details["votes"] = votes_span.get_text(strip=True)
            director_span = soup.find("span", property="v:director")
            if director_span:
                details["director"] = director_span.get_text(strip=True)
            year_span = soup.find("span", property="v:initialReleaseDate")
            if year_span:
                details["year"] = year_span.get_text(strip=True)

            if not rating:
                return None
            return details if details else None
        except Exception as e:
            print(f"Error getting movie details: {e}")
            return None

    def _extract_subject_id_from_url(self, link_url: str) -> Optional[str]:
        match = re.search(r"/subject/(\d+)/", link_url)
        return match.group(1) if match else None

    def _extract_year_from_info(self, info_text: str) -> Optional[int]:
        matches = re.findall(r"(\d{4})", info_text)
        if matches:
            try:
                return int(matches[-1])
            except ValueError:
                pass
        return None

    def _build_rating_result(self, details: Optional[dict], movie_info: dict) -> Optional[RatingResult]:
        rating = 0.0
        if details and details.get("rating"):
            rating = details["rating"]
        elif movie_info.get("rating"):
            try:
                rating = float(movie_info["rating"])
            except (ValueError, TypeError):
                rating = 0.0
        if rating == 0.0:
            return None

        votes = details.get("votes", "") if details else ""
        summary_parts = []
        local_title = details.get("title") if details else movie_info.get("title")
        if local_title:
            summary_parts.append(local_title)
        if votes:
            summary_parts.append(f"{votes} 人评价")
        if details and details.get("director"):
            summary_parts.append(f"导演: {details['director']}")
        if details and details.get("year"):
            summary_parts.append(f"年份: {details['year']}")

        confidence = 0.6
        if details and details.get("votes"):
            confidence += 0.2
        if details and details.get("director"):
            confidence += 0.1
        if details:
            confidence += 0.1

        return RatingResult(
            source=self.source,
            score=rating,
            scale=10.0,
            url=movie_info["url"],
            summary=" | ".join(summary_parts) if summary_parts else "豆瓣评分",
            confidence=min(confidence, 1.0),
            local_title=local_title,
        )
