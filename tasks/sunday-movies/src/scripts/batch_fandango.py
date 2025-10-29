#!/usr/bin/env python3
"""Batch fetch showtimes from multiple theaters on Fandango."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
COLLECTORS_DIR = SUNDAY_MOVIES_ROOT / "src" / "collectors"
if str(COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECTORS_DIR))

from fandango import FandangoShowtimeCollector


# Common theater configurations
THEATERS = {
    "AADYN": {"name": "AMC Mercado 20", "chain": "AMC"},
    "AATUL": {"name": "AMC Eastridge 15", "chain": "AMC"},
    # Add more theaters here
    # "THEATER_ID": {"name": "Theater Name", "chain": "CHAIN_CODE"},
}


def fetch_all_showtimes(
    theaters: Dict[str, Dict[str, str]], target_date: date
) -> Dict[str, List[Dict]]:
    """Fetch showtimes for all theaters on a given date."""
    collector = FandangoShowtimeCollector()
    results = {}
    
    for theater_id, config in theaters.items():
        theater_name = config["name"]
        chain_code = config.get("chain", "AMC")
        
        print(f"🎬 Fetching {theater_name} ({theater_id})...")
        
        try:
            schedules = collector.fetch_showtimes(
                theater_id=theater_id,
                theater_name=theater_name,
                date=target_date,
                chain_code=chain_code,
            )
            
            # Convert to JSON-serializable format
            theater_data = []
            for schedule in schedules:
                movie_data = {
                    "movie_title": schedule.movie_title,
                    "showtimes": []
                }
                
                for showtime in schedule.showtimes:
                    showtime_data = {
                        "start_time": showtime.start_time.isoformat(),
                        "formats": showtime.format_tags,
                        "auditorium": showtime.auditorium,
                        "booking_url": showtime.booking_url,
                    }
                    movie_data["showtimes"].append(showtime_data)
                
                theater_data.append(movie_data)
            
            results[theater_id] = {
                "theater_name": theater_name,
                "chain_code": chain_code,
                "date": target_date.isoformat(),
                "movies": theater_data,
                "movie_count": len(theater_data),
            }
            
            print(f"   ✅ Found {len(theater_data)} movies")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results[theater_id] = {
                "theater_name": theater_name,
                "chain_code": chain_code,
                "date": target_date.isoformat(),
                "error": str(e),
                "movies": [],
                "movie_count": 0,
            }
    
    return results


def print_summary(results: Dict[str, List[Dict]]) -> None:
    """Print a summary of all results."""
    print("\n📊 Summary:")
    total_movies = 0
    successful_theaters = 0
    
    for theater_id, data in results.items():
        theater_name = data["theater_name"]
        movie_count = data["movie_count"]
        
        if "error" not in data:
            successful_theaters += 1
            total_movies += movie_count
            print(f"   ✅ {theater_name}: {movie_count} movies")
        else:
            print(f"   ❌ {theater_name}: Error - {data['error']}")
    
    print(f"\n🎯 Total: {successful_theaters}/{len(results)} theaters, {total_movies} movies")


def main():
    """Main function."""
    if len(sys.argv) > 1:
        target_date = date.fromisoformat(sys.argv[1])
    else:
        target_date = date.today()
    
    print(f"🎬 Batch Fandango Showtime Fetcher")
    print(f"📅 Target date: {target_date}")
    print(f"🏢 Theaters: {len(THEATERS)}")
    
    # Fetch all showtimes
    results = fetch_all_showtimes(THEATERS, target_date)
    
    # Print summary
    print_summary(results)
    
    # Save to JSON file
    output_file = SUNDAY_MOVIES_ROOT / "data" / f"fandango_batch_{target_date.isoformat()}.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
