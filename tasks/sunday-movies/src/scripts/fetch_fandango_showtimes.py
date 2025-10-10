#!/usr/bin/env python3
"""Fetch showtimes from Fandango using the cached cookie file."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[4]
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
COLLECTORS_DIR = SUNDAY_MOVIES_ROOT / "src" / "collectors"
if str(COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECTORS_DIR))

from fandango import FandangoShowtimeCollector

DEFAULT_COOKIE_PATH = SUNDAY_MOVIES_ROOT / "config" / "fandango_cookies.json"


def load_cookies(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Cookie file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {k: v for k, v in data.items() if v}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch showtimes from Fandango")
    parser.add_argument(
        "--theater-id",
        default="AADYN",
        help="Fandango theater ID (e.g. AADYN for AMC Mercado 20)",
    )
    parser.add_argument(
        "--theater-name",
        default="AMC Mercado 20",
        help="Human-friendly theater name used in logs",
    )
    parser.add_argument(
        "--date",
        type=lambda s: date.fromisoformat(s),
        default=date.today(),
        help="ISO date to query (YYYY-MM-DD); defaults to today",
    )
    parser.add_argument(
        "--cookie-file",
        type=Path,
        default=DEFAULT_COOKIE_PATH,
        help="Path to JSON file containing Fandango cookies",
    )
    parser.add_argument(
        "--chain-code",
        default="AMC",
        help="Fandango chain code (default: AMC)",
    )
    parser.add_argument(
        "--referer-slug",
        default=None,
        help="Optional theater slug for Referer header, e.g. amc-mercado-20-aadyn",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy theaterShowtimeGroupings endpoint instead of theaterMovieShowtimes",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw schedule data as JSON for debugging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cookies = load_cookies(args.cookie_file)
    collector = FandangoShowtimeCollector()
    schedules = collector.fetch_showtimes(
        args.theater_id,
        args.theater_name,
        args.date,
        cookies=cookies,
        chain_code=args.chain_code,
        referer_slug=args.referer_slug,
        use_legacy_endpoint=args.legacy,
    )

    if args.raw:
        payload = [
            {
                "movie": schedule.movie_title,
                "showtimes": [
                    {
                        "start_time": show.start_time.isoformat(),
                        "formats": show.format_tags,
                        "auditorium": show.auditorium,
                        "booking_url": show.booking_url,
                    }
                    for show in schedule.showtimes
                ],
            }
            for schedule in schedules
        ]
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return

    if not schedules:
        print("No showtimes returned. Ensure cookies are valid or try another date.")
        return

    print(f"Showtimes for {args.theater_name} on {args.date:%Y-%m-%d}:")
    for schedule in schedules:
        times = ", ".join(format_time(show.start_time) for show in schedule.showtimes)
        print(f"- {schedule.movie_title}: {times}")


def format_time(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


if __name__ == "__main__":
    main()
