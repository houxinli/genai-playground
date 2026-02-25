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
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
SRC_DIR = SUNDAY_MOVIES_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fetch_showtimes_with_all_ratings import (  # type: ignore
    fetch_showtimes_with_all_ratings,
    print_summary,
    format_markdown_table,
    save_results,
    RATING_COLUMNS,
)
from notifier.email import send_markdown_email  # type: ignore
from ratings.base import RatingResult  # type: ignore
from ratings.utils import normalize_title  # type: ignore




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
    parser.add_argument(
        "--markdown-output",
        type=Path,
        help="Optional file to save rendered Markdown tables",
    )
    parser.add_argument(
        "--email-to",
        action="append",
        help="Send the markdown summary to the specified email (can repeat)",
    )
    parser.add_argument(
        "--email-subject",
        type=str,
        default=None,
        help="Subject when sending email notifications",
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

    markdown_lines: Optional[List[str]] = None
    if args.markdown_output or args.email_to:
        markdown_lines = [f"# Sunday Movies Showtimes ({args.date})", ""]

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
        table_md = format_markdown_table(results, theater_name)
        print("\n" + table_md)
        if markdown_lines is not None:
            markdown_lines.append(f"## {theater_name}")
            markdown_lines.append("")
            markdown_lines.append(table_md)
            markdown_lines.append("")
        theater_results.append((theater_name, results))

        if args.output_dir:
            output_path = (
                args.output_dir
                / f"{theater_id.lower()}_{args.date.isoformat()}_multi.json"
            )
            save_results(results, output_path)

    if theater_results:
        print("\n" + "=" * 80)
        combined_md = format_combined_markdown_table(theater_results)
        print("🧮 Combined Schedule (all theaters)")
        print("\n" + combined_md)
        if markdown_lines is not None:
            markdown_lines.append("## Combined Schedule")
            markdown_lines.append("")
            markdown_lines.append(combined_md)
            markdown_lines.append("")

    if markdown_lines is not None:
        markdown_text = "\n".join(markdown_lines)
        if args.markdown_output:
            output_path = args.markdown_output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown_text, encoding="utf-8")
            print(f"\n📝 Markdown saved to {output_path}")
        if args.email_to:
            subject = args.email_subject or f"Sunday Movies Showtimes - {args.date}"
            send_markdown_email(markdown_text, subject=subject, to_addresses=args.email_to)
            print(f"✉️  Email sent to: {', '.join(args.email_to)}")


def format_combined_markdown_table(theater_results: List[Tuple[str, List[Dict]]]) -> str:
    """Return a Markdown table showing unique ratings per platform plus theater showtimes."""
    theater_names = [name for name, _ in theater_results]
    header_cols = ["English Title", "中文标题"]
    header_cols.extend(label for _, label in RATING_COLUMNS)
    for name in theater_names:
        header_cols.append(f"Showtimes · {name}")

    lines = [
        "| " + " | ".join(header_cols) + " |",
        "| " + " | ".join(["---"] * len(header_cols)) + " |",
    ]

    merged: Dict[str, Dict] = {}
    for theater_name, movies in theater_results:
        for movie in movies:
            key = normalize_title(movie["title"])
            entry = merged.setdefault(
                key,
                {
                    "english": movie["title"],
                    "chinese": movie.get("local_title"),
                    "ratings": {},
                    "showtimes": {},
                },
            )
            if not entry.get("chinese") and movie.get("local_title"):
                entry["chinese"] = movie["local_title"]

            ratings = movie.get("ratings", {})
            for source, _ in RATING_COLUMNS:
                if source in ratings and source not in entry["ratings"]:
                    entry["ratings"][source] = ratings[source]

            count, showtime_text = summarize_showtimes(movie["showtimes"])
            entry["showtimes"][theater_name] = showtime_text
            entry["total_count"] = entry.get("total_count", 0) + count

    sorted_movies = sorted(
        merged.values(),
        key=lambda item: item.get("total_count", 0),
        reverse=True,
    )

    for item in sorted_movies:
        row = [item["english"], item.get("chinese") or "—"]
        for source, _ in RATING_COLUMNS:
            rating_data = item["ratings"].get(source)
            if rating_data and rating_data.get("score") is not None:
                row.append(f"{rating_data['score']:.1f}/10")
            else:
                row.append("—")
        for theater_name in theater_names:
            row.append(item["showtimes"].get(theater_name, "—"))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


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
