#!/usr/bin/env python3
"""Aggregate movie ratings for the Fandango showtime list."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

SCRIPT_PATH = Path(__file__).resolve()
SRC_ROOT = SCRIPT_PATH.parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ratings import (
    DoubanFetcher,
    ImdbFetcher,
    RatingsAggregator,
    RatingResult,
    RottenTomatoesFetcher,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch ratings for Fandango showtimes")
    parser.add_argument(
        "fandango_json",
        type=Path,
        help="Path to Fandango JSON (viewModel) file",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Limit number of movies to process",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=["douban", "imdb", "rottentomatoes"],
        help="Limit rating providers (defaults to all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human readable text",
    )
    return parser.parse_args()


def load_movies(path: Path, limit: Optional[int]) -> Iterable[tuple[str, Optional[int]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    view_model = payload.get("viewModel") or {}
    movies = view_model.get("movies") or []
    for movie in movies[: limit or None]:
        title = movie.get("title") or movie.get("name")
        year = movie.get("releaseDate")
        year_int: Optional[int] = None
        if isinstance(year, int):
            year_int = year
        elif isinstance(year, str) and year[:4].isdigit():
            year_int = int(year[:4])
        if title:
            yield title, year_int


def build_aggregator(selected: Optional[list[str]]) -> RatingsAggregator:
    fetchers = []
    mapping = {
        "douban": DoubanFetcher,
        "imdb": ImdbFetcher,
        "rottentomatoes": RottenTomatoesFetcher,
    }
    use = selected or list(mapping.keys())
    for key in use:
        fetchers.append(mapping[key]())
    return RatingsAggregator(fetchers)


def format_result(title: str, year: Optional[int], ratings: list[RatingResult]) -> str:
    header = f"{title} ({year})" if year else title
    if not ratings:
        return f"- {header}: no ratings"
    parts = [f"{r.source}: {r.score}/{r.scale}" for r in ratings]
    return f"- {header}: " + ", ".join(parts)


def main() -> None:
    args = parse_args()
    aggregator = build_aggregator(args.provider)

    results = []
    for title, year in load_movies(args.fandango_json, args.top):
        ratings = aggregator.fetch(title, year=year)
        results.append((title, year, ratings))

    if args.json:
        data = [
            {
                "title": title,
                "year": year,
                "ratings": [
                    {
                        "source": rating.source,
                        "score": rating.score,
                        "scale": rating.scale,
                        "url": rating.url,
                        "summary": rating.summary,
                        "confidence": rating.confidence,
                    }
                    for rating in ratings
                ],
            }
            for title, year, ratings in results
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    for title, year, ratings in results:
        print(format_result(title, year, ratings))


if __name__ == "__main__":
    main()
