#!/usr/bin/env python3
"""Fetch Sunday Movies data for multiple theaters and print combined Markdown tables."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_DIR = SCRIPT_PATH.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fetch_showtimes_with_all_ratings import (  # type: ignore
    fetch_showtimes_with_all_ratings,
    print_summary,
    print_markdown_table,
    save_results,
)
from ratings.base import RatingResult  # type: ignore
from ratings.utils import normalize_title  # type: ignore

RATING_COLUMNS = [
    ("douban", "豆瓣"),
    ("imdb", "IMDb"),
    ("rottentomatoes_critics", "RT Critics"),
    ("rottentomatoes_audience", "RT Audience"),
]


DEFAULT_THEATERS: List[Tuple[str, str]] = [
    ("AADYN", "AMC Mercado 20"),
    ("AATUL", "AMC Eastridge 15"),
]


def parse_theater(arg: str) -> Tuple[str, str]:
    if ":" not in arg:
        raise argparse.ArgumentTypeError(
            "Theater must be in the format ID:Name (e.g. AADYN:\"AMC Mercado 20\")"
        )
    theater_id, theater_name = arg.split(":", 1)
    theater_id = theater_id.strip()
    theater_name = theater_name.strip().strip('"').strip("'")
    if not theater_id or not theater_name:
        raise argparse.ArgumentTypeError("Invalid theater format; ID or name missing")
    return theater_id, theater_name


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch multi-theater showtimes with ratings and output Markdown tables"
    )
    parser.add_argument(
        "--theater",
        action="append",
        type=parse_theater,
        help="Specify theater as ID:Name (can be repeated). Default: AMC Mercado 20 + AMC Eastridge 15",
    )
    parser.add_argument(
        "--date",
        type=lambda s: date.fromisoformat(s),
        default=date.today(),
        help="Date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-movies",
        type=int,
        default=0,
        help="Maximum number of movies per theater (0 = all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory to store per-theater JSON results",
    )
    parser.add_argument(
        "--min-time",
        type=str,
        help="Only include showtimes at or after HH:MM (24h)",
    )
    parser.add_argument(
        "--max-time",
        type=str,
        help="Only include showtimes at or before HH:MM (24h)",
    )

    args = parser.parse_args()

    theaters = args.theater if args.theater else DEFAULT_THEATERS

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    max_movies = args.max_movies if args.max_movies > 0 else None
    shared_rating_cache: Dict[str, List[RatingResult]] = {}

    min_minutes = _parse_time_arg(args.min_time)
    max_minutes = _parse_time_arg(args.max_time)

    print(f"🎬 Sunday Movies Multi-Theater Fetcher")
    print(f"📅 Date: {args.date}")
    max_desc = args.max_movies if max_movies is not None else "All"
    print(f"🏢 Theaters: {len(theaters)} (max {max_desc} movies each)")
    if min_minutes is not None or max_minutes is not None:
        print(f"🕒 Time window: {args.min_time or '--'} - {args.max_time or '--'}")

    theater_results: List[Tuple[str, List[Dict]]] = []

    for theater_id, theater_name in theaters:
        print("\n" + "=" * 80)
        print(f"🎭 Theater: {theater_name} ({theater_id})")
        results = fetch_showtimes_with_all_ratings(
            theater_id=theater_id,
            theater_name=theater_name,
            target_date=args.date,
            max_movies=max_movies,
            rating_cache=shared_rating_cache,
            min_minutes=min_minutes,
            max_minutes=max_minutes,
        )
        if not results:
            print("❌ No results for this theater")
            continue

        print_summary(results)
        print_markdown_table(results, theater_name)
        theater_results.append((theater_name, results))

        if args.output_dir:
            output_path = (
                args.output_dir
                / f"{theater_id.lower()}_{args.date.isoformat()}_multi.json"
            )
            save_results(results, output_path)

    if theater_results:
        print("\n" + "=" * 80)
        print("🧮 Combined Schedule (all theaters)")
        print_combined_markdown_table(theater_results)


def print_combined_markdown_table(theater_results: List[Tuple[str, List[Dict]]]) -> None:
    """Print a single Markdown table with columns per theater."""
    theater_names = [name for name, _ in theater_results]
    header_cols = ["English Title", "中文标题"]
    for name in theater_names:
        for _, label in RATING_COLUMNS:
            header_cols.append(f"{label} · {name}")
        header_cols.append(f"Showtimes · {name}")

    print("| " + " | ".join(header_cols) + " |")
    print("| " + " | ".join(["---"] * len(header_cols)) + " |")

    merged: Dict[str, Dict] = {}
    for theater_name, movies in theater_results:
        for movie in movies:
            key = normalize_title(movie["title"])
            entry = merged.setdefault(
                key,
                {
                    "english": movie["title"],
                    "chinese": movie.get("local_title"),
                    "by_theater": {},
                },
            )
            if not entry.get("chinese") and movie.get("local_title"):
                entry["chinese"] = movie["local_title"]

            score = movie.get("aggregated_score")
            count, showtime_text = summarize_showtimes(movie["showtimes"])
            entry["by_theater"][theater_name] = {
                "aggregated": score,
                "ratings": movie["ratings"],
                "count": count,
                "text": showtime_text,
            }

    sorted_movies = sorted(
        merged.values(),
        key=lambda item: sum(
            entry.get("count", 0) for entry in item["by_theater"].values()
        ),
        reverse=True,
    )

    for item in sorted_movies:
        row = [item["english"], item.get("chinese") or "—"]
        for theater_name in theater_names:
            data = item["by_theater"].get(theater_name)
            ratings = data.get("ratings") if data else None
            for source, _ in RATING_COLUMNS:
                cell = "—"
                if ratings and source in ratings:
                    rating_data = ratings[source]
                    score = rating_data.get("score")
                    scale = rating_data.get("scale", 10)
                    if score is not None:
                        cell = f"{score:.1f}/{scale}"
                row.append(cell)
            row.append(data["text"] if data else "—")
        print("| " + " | ".join(row) + " |")


def summarize_showtimes(showtimes: List[Dict]) -> Tuple[int, str]:
    times: List[str] = []
    for show in showtimes:
        start = show.get("start_time")
        if not start:
            continue
        try:
            dt = datetime.fromisoformat(start)
            times.append(dt.strftime("%H:%M"))
        except Exception:
            continue
    times.sort()
    if not times:
        return 0, "—"
    return len(times), f"{len(times)} 场: {', '.join(times)}"


def _parse_time_arg(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        hour_str, minute_str = value.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        return hour * 60 + minute
    except ValueError:
        raise SystemExit(f"Invalid time format '{value}'. Expected HH:MM 24h format.")


if __name__ == "__main__":
    main()
