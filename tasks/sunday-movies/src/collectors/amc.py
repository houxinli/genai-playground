"""AMC showtime collector."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, Iterable, List, Optional

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore

try:  # pragma: no cover - import path shim for direct module execution
    from .models import MovieSchedule, Showtime
except ImportError:  # pragma: no cover
    from models import MovieSchedule, Showtime  # type: ignore

try:
    import cloudscraper
except ImportError:  # pragma: no cover - optional dependency
    cloudscraper = None

logger = logging.getLogger(__name__)


class AMCShowtimeCollector:
    """Scrape AMC theatre showtimes for a given date."""

    BASE_URL = "https://www.amctheatres.com"
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        timeout: int = 15,
        user_agent: str = "Mozilla/5.0 (SundayMoviesBot)",
    ) -> None:
        if BeautifulSoup is None:
            raise ImportError("BeautifulSoup (bs4) is required for AMC scraping. Install beautifulsoup4.")
        if session is not None:
            self.session = session
        elif cloudscraper is not None:
            # cloudscraper 可自动处理 Cloudflare 防护，缺失时回退到标准 requests
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "linux", "mobile": False},
                delay=5,
            )
        else:
            self.session = requests.Session()
        self.timeout = timeout
        # 叠加更完整的浏览器头，降低 403 概率
        for key, value in self.DEFAULT_HEADERS.items():
            self.session.headers.setdefault(key, value)
        self.session.headers.setdefault("User-Agent", user_agent)

    def fetch_theatre_showtimes(
        self,
        theatre_slug: str,
        date: dt.date,
    ) -> List[MovieSchedule]:
        """Fetch showtimes for a specific theatre and date."""
        url = f"{self.BASE_URL}/movie-theatres/{theatre_slug}"
        params = {"date": date.isoformat()}
        logger.debug("Fetching AMC showtimes", extra={"url": url, "params": params})
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return self._parse_showtimes_html(response.text, theatre_slug, date)

    def _parse_showtimes_html(
        self,
        html: str,
        theatre_slug: str,
        date: dt.date,
    ) -> List[MovieSchedule]:
        """Parse AMC showtime HTML page."""
        soup = BeautifulSoup(html, "html.parser")
        listing_container = soup.select_one("div[data-qa='showtimes-list']")
        if not listing_container:
            logger.warning("AMC showtime list not found", extra={"theatre": theatre_slug, "date": date})
            return []

        movie_blocks = listing_container.select("div.ShowtimeCard")
        schedules: Dict[str, List[Showtime]] = {}

        for movie_block in movie_blocks:
            title_element = movie_block.select_one("[data-qa='showtime-card-title']")
            if not title_element:
                continue
            movie_title = title_element.get_text(strip=True)

            for button in movie_block.select("a[data-qa='showtime-button']"):
                time_text = button.get_text(strip=True)
                try:
                    start_time = self._combine_date_time(date, time_text)
                except ValueError:
                    logger.debug("Skip unparsable showtime", extra={"time_text": time_text})
                    continue

                booking_href = button.get("href")
                booking_url = f"{self.BASE_URL}{booking_href}" if booking_href else None
                format_tags = [tag.get_text(strip=True) for tag in button.select("span.Showtime__format")]

                showtime = Showtime(
                    cinema_id=theatre_slug,
                    cinema_name=theatre_slug.replace("-", " ").title(),
                    movie_title=movie_title,
                    start_time=start_time,
                    format_tags=format_tags,
                    booking_url=booking_url,
                )
                schedules.setdefault(movie_title, []).append(showtime)

        return [
            MovieSchedule(movie_title=title, showtimes=sorted(shows, key=lambda s: s.start_time))
            for title, shows in schedules.items()
        ]

    @staticmethod
    def _combine_date_time(date: dt.date, time_text: str) -> dt.datetime:
        """Combine ISO date with strings like '12:30 PM'."""
        normalized = time_text.replace(".", "").upper()
        for fmt in ("%I:%M %p", "%I %p"):
            try:
                time_part = dt.datetime.strptime(normalized, fmt).time()
                return dt.datetime.combine(date, time_part)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse time: {time_text}")

    @staticmethod
    def flatten_schedules(schedules: Iterable[MovieSchedule]) -> List[Showtime]:
        """Flatten grouped schedules into a single list."""
        return [show for schedule in schedules for show in schedule.showtimes]
