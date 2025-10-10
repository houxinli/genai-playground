"""Fandango showtime collector."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, Iterable, List, Optional

import requests
from dateutil import parser as date_parser

try:  # pragma: no cover - import shim for script usage
    from .models import MovieSchedule, Showtime
except ImportError:  # pragma: no cover
    from models import MovieSchedule, Showtime  # type: ignore

logger = logging.getLogger(__name__)


class FandangoAuthError(RuntimeError):
    """Raised when Fandango blocks the request due to missing session context."""


class FandangoShowtimeCollector:
    """Fetch showtimes from Fandango's theater pages."""

    LEGACY_API_TEMPLATE = "https://www.fandango.com/napi/theatershowtimegroupings/{theater_id}/{iso_date}"
    THEATER_MOVIE_SHOWTIMES_TEMPLATE = (
        "https://www.fandango.com/napi/theaterMovieShowtimes/"
        "{theater_id}?chainCode={chain_code}&startDate={iso_date}&isdesktop=true&partnerRestrictedTicketing="
    )
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    }

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        timeout: int = 15,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        for key, value in self.DEFAULT_HEADERS.items():
            self.session.headers.setdefault(key, value)

    def fetch_showtimes(
        self,
        theater_id: str,
        theater_name: str,
        date: dt.date,
        *,
        cookies: Optional[Dict[str, str]] = None,
        chain_code: str = "AMC",
        referer_slug: Optional[str] = None,
        use_legacy_endpoint: bool = False,
    ) -> List[MovieSchedule]:
        """Return grouped showtimes for a given theater and date."""

        iso_date = date.isoformat()
        if use_legacy_endpoint:
            url = self.LEGACY_API_TEMPLATE.format(theater_id=theater_id.lower(), iso_date=iso_date)
        else:
            url = self.THEATER_MOVIE_SHOWTIMES_TEMPLATE.format(
                theater_id=theater_id,
                chain_code=chain_code,
                iso_date=iso_date,
            )

        headers = {}
        if referer_slug:
            headers["Referer"] = (
                f"https://www.fandango.com/{referer_slug}/theater-page?format=all&date={iso_date}"
            )
        elif "Referer" not in self.session.headers:
            headers["Referer"] = "https://www.fandango.com/"

        logger.debug(
            "Fetching Fandango showtimes",
            extra={"url": url, "theater_id": theater_id, "chain_code": chain_code, "legacy": use_legacy_endpoint},
        )

        response = self.session.get(url, timeout=self.timeout, cookies=cookies, headers=headers or None)
        if response.status_code == 403:
            raise FandangoAuthError("Fandango rejected the request (HTTP 403). Provide cookies or retry manually.")
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Unexpected non-JSON response from Fandango") from exc

        return self._parse_groupings(payload, theater_id, theater_name, iso_date)

    def _parse_groupings(
        self,
        payload: Dict,
        theater_id: str,
        theater_name: str,
        iso_date: str,
    ) -> List[MovieSchedule]:
        groupings = self._extract_grouping_root(payload)
        if not groupings:
            view_model = payload.get("viewModel")
            if view_model:
                return self._parse_view_model(view_model, theater_id, theater_name, iso_date)
            logger.info("No showtime groupings returned", extra={"theater_id": theater_id})
            return []

        return self._parse_legacy_groupings(groupings, theater_id, theater_name)

    def _parse_legacy_groupings(
        self,
        groupings: Dict,
        theater_id: str,
        theater_name: str,
    ) -> List[MovieSchedule]:
        schedules: Dict[str, List[Showtime]] = {}
        for date_block in groupings.get("dates", []):
            base_date = self._extract_date(date_block)
            if base_date is None:
                continue

            for movie in date_block.get("movies", []):
                title = self._extract_movie_title(movie)
                if not title:
                    continue

                for show in movie.get("showtimes", []):
                    start_time = self._extract_showtime_datetime(show, base_date)
                    if start_time is None:
                        continue

                    showtime = Showtime(
                        cinema_id=theater_id,
                        cinema_name=theater_name,
                        movie_title=title,
                        start_time=start_time,
                        format_tags=self._extract_format_tags(show, movie),
                        booking_url=self._extract_booking_url(show),
                        auditorium=self._extract_auditorium(show),
                    )
                    schedules.setdefault(title, []).append(showtime)

        return [
            MovieSchedule(movie_title=title, showtimes=sorted(show_list, key=lambda s: s.start_time))
            for title, show_list in schedules.items()
        ]

    def _parse_view_model(
        self,
        view_model: Dict,
        theater_id: str,
        theater_name: str,
        iso_date: str,
    ) -> List[MovieSchedule]:
        schedules: Dict[str, List[Showtime]] = {}
        selected_date = view_model.get("date") or iso_date
        movies = view_model.get("movies") or []

        for movie in movies:
            title = movie.get("title") or movie.get("name")
            if not title:
                continue

            for variant in movie.get("variants") or []:
                variant_format = variant.get("format")
                for group in variant.get("amenityGroups") or []:
                    amenity_names = [
                        str(amenity.get("name")).strip()
                        for amenity in group.get("amenities") or []
                        if amenity.get("name")
                    ]

                    for show in group.get("showtimes") or []:
                        start_time = self._parse_ticketing_date(show, selected_date)
                        if start_time is None:
                            continue

                        format_tags = self._collect_view_model_tags(
                            variant_format,
                            amenity_names,
                            show.get("filmFormat") or [],
                        )

                        showtime = Showtime(
                            cinema_id=theater_id,
                            cinema_name=theater_name,
                            movie_title=title,
                            start_time=start_time,
                            format_tags=format_tags,
                            booking_url=show.get("ticketingJumpPageURL"),
                            auditorium=show.get("auditorium") or show.get("auditoriumName"),
                        )
                        schedules.setdefault(title, []).append(showtime)

        return [
            MovieSchedule(movie_title=title, showtimes=sorted(show_list, key=lambda s: s.start_time))
            for title, show_list in schedules.items()
        ]

    @staticmethod
    def _collect_view_model_tags(
        variant_format: Optional[str],
        amenity_names: Iterable[str],
        film_format: Iterable[Dict[str, Any]],
    ) -> List[str]:
        tags: List[str] = []

        def add(tag: Optional[str]) -> None:
            if not tag:
                return
            tag = str(tag).strip()
            if tag and tag not in tags:
                tags.append(tag)

        add(variant_format)
        for name in amenity_names:
            add(name)
        for fmt in film_format:
            add(fmt.get("filterName") or fmt.get("name"))

        return tags

    @staticmethod
    def _parse_ticketing_date(show: Dict, selected_date: str) -> Optional[dt.datetime]:
        ticketing_date = show.get("ticketingDate")
        if ticketing_date:
            normalized = ticketing_date.replace("+", " ")
            try:
                parsed = date_parser.parse(normalized)
                if parsed.tzinfo:
                    return parsed.astimezone(None).replace(tzinfo=None)
                return parsed
            except (ValueError, TypeError):
                pass

        time_str = show.get("screenReaderTime") or show.get("date")
        if selected_date and time_str:
            try:
                parsed = date_parser.parse(f"{selected_date} {time_str}")
                if parsed.tzinfo:
                    return parsed.astimezone(None).replace(tzinfo=None)
                return parsed
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def _extract_grouping_root(payload: Dict) -> Optional[Dict]:
        """Support both top-level and GraphQL style responses."""
        if not payload:
            return None
        if "dates" in payload:
            return payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if not data:
            return None
        groupings = data.get("theaterShowtimeGroupings") or data.get("theaterShowtimes")
        return groupings

    @staticmethod
    def _extract_date(date_block: Dict) -> Optional[dt.date]:
        date_str = (
            date_block.get("date")
            or date_block.get("showDate")
            or date_block.get("day")
            or date_block.get("dateText")
        )
        if not date_str:
            return None
        try:
            parsed = date_parser.parse(str(date_str))
        except (ValueError, TypeError):
            return None
        return parsed.date()

    @staticmethod
    def _extract_movie_title(movie: Dict) -> Optional[str]:
        return (
            movie.get("name")
            or movie.get("movieName")
            or movie.get("title")
            or movie.get("movieTitle")
        )

    @staticmethod
    def _extract_showtime_datetime(show: Dict, base_date: dt.date) -> Optional[dt.datetime]:
        candidates = [
            show.get("startDateTimeLocal"),
            show.get("startDateTime"),
            show.get("displayDateTime"),
            show.get("startTime"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = date_parser.parse(str(candidate))
                if not parsed.tzinfo:
                    return dt.datetime.combine(base_date, parsed.time())
                return parsed.astimezone(None).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue

        # fallback when only a time string is provided
        time_str = show.get("time") or show.get("startTimeText")
        if not time_str:
            return None
        try:
            time_obj = date_parser.parse(time_str).time()
        except (ValueError, TypeError):
            return None
        return dt.datetime.combine(base_date, time_obj)

    @staticmethod
    def _extract_format_tags(show: Dict, movie: Dict) -> List[str]:
        tags: List[str] = []

        for field in ("attributes", "attributeCodes", "amenities", "amenityCodes"):
            value = show.get(field)
            if isinstance(value, list):
                tags.extend(str(v) for v in value if v)

        # Some variants list formats at the movie level
        movie_formats = movie.get("formats") or movie.get("formatTypes")
        if isinstance(movie_formats, list):
            tags.extend(str(item) for item in movie_formats if item)

        return sorted({tag.strip() for tag in tags if isinstance(tag, str)})

    @staticmethod
    def _extract_booking_url(show: Dict) -> Optional[str]:
        url = (
            show.get("ticketingUrl")
            or show.get("purchaseUrl")
            or show.get("ticketUrl")
        )
        if url and isinstance(url, str):
            return url
        return None

    @staticmethod
    def _extract_auditorium(show: Dict) -> Optional[str]:
        auditorium = show.get("auditorium") or show.get("auditoriumName")
        if auditorium and isinstance(auditorium, str):
            return auditorium.strip()
        return None

    @staticmethod
    def flatten_schedules(schedules: Iterable[MovieSchedule]) -> List[Showtime]:
        """Flatten grouped schedules into a single list."""
        return [show for schedule in schedules for show in schedule.showtimes]
