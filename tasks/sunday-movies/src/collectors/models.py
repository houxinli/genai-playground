"""Common collector models."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Showtime:
    """Single showtime entry."""

    cinema_id: str
    cinema_name: str
    movie_title: str
    start_time: dt.datetime
    format_tags: List[str] = field(default_factory=list)
    booking_url: Optional[str] = None
    auditorium: Optional[str] = None


@dataclass
class MovieSchedule:
    """Showtimes grouped by movie."""

    movie_title: str
    showtimes: List[Showtime]
