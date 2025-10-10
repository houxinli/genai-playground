"""Unit tests for Fandango showtime collector parsing."""

from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

import requests

_FILE = Path(__file__).resolve()
_MODULE_DIR = _FILE.parent
_REPO_ROOT = _FILE.parents[4]

for path in (str(_MODULE_DIR), str(_REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from fandango import FandangoShowtimeCollector

GROUPINGS_FIXTURE_PATH = (
    _REPO_ROOT / "tasks" / "sunday-movies" / "tests" / "data" / "fandango_groupings.json"
)

VIEW_MODEL_FIXTURE_PATH = (
    _REPO_ROOT / "tasks" / "sunday-movies" / "tests" / "data" / "fandango_view_model.json"
)


class FandangoShowtimeCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = FandangoShowtimeCollector(session=requests.Session())

    def test_parse_groupings_into_schedules(self) -> None:
        payload = json.loads(GROUPINGS_FIXTURE_PATH.read_text())
        schedules = self.collector._parse_groupings(
            payload,
            theater_id="AADYN",
            theater_name="AMC Mercado 20",
            iso_date="2025-10-12",
        )

        self.assertEqual(len(schedules), 2)

        dune = next(schedule for schedule in schedules if schedule.movie_title == "Dune: Part Two")
        dune_times = [show.start_time.strftime("%H:%M") for show in dune.showtimes]
        self.assertEqual(dune_times, ["13:30", "16:15"])
        self.assertEqual(dune.showtimes[0].format_tags, ["Dolby Cinema", "IMAX", "Reserved Seating"])
        self.assertEqual(dune.showtimes[0].auditorium, "Auditorium 5")

        inside_out = next(schedule for schedule in schedules if schedule.movie_title == "Inside Out 2")
        self.assertEqual(len(inside_out.showtimes), 1)
        self.assertEqual(
            inside_out.showtimes[0].start_time,
            dt.datetime(2025, 10, 12, 12, 0),
        )

    def test_flatten_schedules_returns_all_showtimes(self) -> None:
        payload = json.loads(GROUPINGS_FIXTURE_PATH.read_text())
        schedules = self.collector._parse_groupings(
            payload,
            theater_id="AADYN",
            theater_name="AMC Mercado 20",
            iso_date="2025-10-12",
        )
        flat = FandangoShowtimeCollector.flatten_schedules(schedules)
        self.assertEqual(len(flat), 3)
        self.assertTrue(all(show.cinema_id == "AADYN" for show in flat))

    def test_parse_view_model_payload(self) -> None:
        payload = json.loads(VIEW_MODEL_FIXTURE_PATH.read_text())
        schedules = self.collector._parse_groupings(
            payload,
            theater_id="AADYN",
            theater_name="AMC Mercado 20",
            iso_date="2025-10-12",
        )

        self.assertEqual(len(schedules), 1)
        schedule = schedules[0]
        self.assertEqual(schedule.movie_title, "Sample Movie")
        self.assertEqual(len(schedule.showtimes), 2)
        first_tags = schedule.showtimes[0].format_tags
        self.assertIn("Dolby Cinema", first_tags)
        self.assertIn("Reserved seating", first_tags)
        self.assertIn("Dolby", first_tags)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
