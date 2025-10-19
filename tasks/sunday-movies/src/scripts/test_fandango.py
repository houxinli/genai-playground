#!/usr/bin/env python3
"""Test script for Fandango showtime fetching functionality."""

import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
COLLECTORS_DIR = SUNDAY_MOVIES_ROOT / "src" / "collectors"
if str(COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECTORS_DIR))

from fandango import FandangoShowtimeCollector


def test_theater(theater_id: str, theater_name: str, test_date: date) -> bool:
    """Test a single theater and date."""
    print(f"\n🧪 Testing {theater_name} ({theater_id}) on {test_date}")
    
    collector = FandangoShowtimeCollector()
    
    try:
        schedules = collector.fetch_showtimes(
            theater_id=theater_id,
            theater_name=theater_name,
            date=test_date,
        )
        
        if schedules:
            print(f"✅ Success: Found {len(schedules)} movies")
            for schedule in schedules[:3]:  # Show first 3 movies
                times = ", ".join(
                    show.start_time.strftime("%I:%M %p").lstrip("0")
                    for show in schedule.showtimes[:3]
                )
                print(f"   - {schedule.movie_title}: {times}")
            return True
        else:
            print("❌ No showtimes found")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run tests on various theaters."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    # Test theaters (theater_id, theater_name)
    theaters = [
        ("AADYN", "AMC Mercado 20"),
        # Add more theaters here for testing
    ]
    
    print("🎬 Fandango Showtime Fetcher Test Suite")
    print(f"📅 Testing dates: {today}, {tomorrow}")
    
    results = []
    for theater_id, theater_name in theaters:
        for test_date in [today, tomorrow]:
            success = test_theater(theater_id, theater_name, test_date)
            results.append((theater_id, theater_name, test_date, success))
    
    # Summary
    print("\n📊 Test Summary:")
    total_tests = len(results)
    successful_tests = sum(1 for _, _, _, success in results if success)
    
    for theater_id, theater_name, test_date, success in results:
        status = "✅" if success else "❌"
        print(f"   {status} {theater_name} ({theater_id}) on {test_date}")
    
    print(f"\n🎯 Results: {successful_tests}/{total_tests} tests passed")
    
    if successful_tests == total_tests:
        print("🎉 All tests passed! Fandango fetcher is working correctly.")
    elif successful_tests > 0:
        print("⚠️  Some tests passed. Fetcher is partially working.")
    else:
        print("🚨 All tests failed. There may be an issue with the fetcher.")


if __name__ == "__main__":
    main()
