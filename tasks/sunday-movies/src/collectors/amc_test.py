"""Unit tests for AMC showtime collector."""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

import requests

try:
    import bs4  # type: ignore
except ImportError:
    bs4 = None

_FILE = Path(__file__).resolve()
_MODULE_DIR = _FILE.parent
_REPO_ROOT = _FILE.parents[4]
for path in (str(_MODULE_DIR), str(_REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from amc import AMCShowtimeCollector

SAMPLE_HTML = """
<div data-qa="showtimes-list">
  <div class="ShowtimeCard">
    <h3 data-qa="showtime-card-title">Dune: Part Two</h3>
    <div class="Showtime__times">
      <a data-qa="showtime-button" href="/movie-theatres/ticketing/some-id">
        1:30 PM
        <span class="Showtime__format">IMAX</span>
      </a>
      <a data-qa="showtime-button" href="/movie-theatres/ticketing/some-id-2">
        4:15 PM
        <span class="Showtime__format">Dolby Cinema</span>
      </a>
    </div>
  </div>
  <div class="ShowtimeCard">
    <h3 data-qa="showtime-card-title">Inside Out 2</h3>
    <div class="Showtime__times">
      <a data-qa="showtime-button" href="/movie-theatres/ticketing/another-id">
        12:00 PM
      </a>
    </div>
  </div>
</div>
"""


@unittest.skipUnless(bs4 is not None, "beautifulsoup4 is required for AMC collector tests")
class AMCShowtimeCollectorParseTests(unittest.TestCase):
    def setUp(self) -> None:
        # 使用显式 requests.Session 避免测试时触发真实 Cloudflare 解决方案
        self.collector = AMCShowtimeCollector(session=requests.Session())
        self.test_date = dt.date(2025, 1, 5)

    def test_parse_showtimes_creates_grouped_schedules(self) -> None:
        schedules = self.collector._parse_showtimes_html(
            SAMPLE_HTML,
            theatre_slug="san-jose/amc-mercado-20",
            date=self.test_date,
        )

        self.assertEqual(len(schedules), 2)

        dune_schedule = next(schedule for schedule in schedules if schedule.movie_title == "Dune: Part Two")
        times = [show.start_time.strftime("%H:%M") for show in dune_schedule.showtimes]
        self.assertEqual(times, ["13:30", "16:15"])
        self.assertEqual(dune_schedule.showtimes[0].format_tags, ["IMAX"])
        self.assertTrue(dune_schedule.showtimes[0].booking_url.endswith("some-id"))

        inside_out_schedule = next(
            schedule for schedule in schedules if schedule.movie_title == "Inside Out 2"
        )
        self.assertEqual(len(inside_out_schedule.showtimes), 1)
        self.assertEqual(
            inside_out_schedule.showtimes[0].start_time,
            dt.datetime.combine(self.test_date, dt.time(hour=12)),
        )

    def test_flatten_schedules_returns_all_showtimes(self) -> None:
        schedules = self.collector._parse_showtimes_html(
            SAMPLE_HTML,
            theatre_slug="san-jose/amc-mercado-20",
            date=self.test_date,
        )
        flat = AMCShowtimeCollector.flatten_schedules(schedules)
        self.assertEqual(len(flat), 3)
        self.assertTrue(all(show.cinema_id == "san-jose/amc-mercado-20" for show in flat))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
