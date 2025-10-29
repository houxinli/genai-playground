#!/usr/bin/env python3
"""Script to help find Fandango theater IDs."""

import requests
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SUNDAY_MOVIES_ROOT = SCRIPT_PATH.parents[2]
COLLECTORS_DIR = SUNDAY_MOVIES_ROOT / "src" / "collectors"
if str(COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECTORS_DIR))

from fandango import FandangoShowtimeCollector


def test_theater_id(theater_id: str, theater_name: str, date_str: str = "2025-10-19") -> bool:
    """Test if a theater ID works."""
    collector = FandangoShowtimeCollector()
    
    try:
        from datetime import date
        test_date = date.fromisoformat(date_str)
        
        schedules = collector.fetch_showtimes(
            theater_id=theater_id,
            theater_name=theater_name,
            date=test_date,
        )
        
        if schedules:
            print(f"✅ Found {theater_id}: {len(schedules)} movies")
            for schedule in schedules[:3]:
                print(f"   - {schedule.movie_title}")
            return True
        else:
            print(f"❌ No data for {theater_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error for {theater_id}: {e}")
        return False


def search_amc_eastridge():
    """Search for AMC Eastridge 15 theater ID."""
    print("🔍 Searching for AMC Eastridge 15 theater ID...")
    
    # Common patterns for AMC theater IDs
    possible_ids = [
        "EASTRIDGE",
        "EASTRIDGE15", 
        "AMCEASTRIDGE",
        "AMCEASTRIDGE15",
        "EASTRIDGE_15",
        "AMC_EASTRIDGE_15",
        "EASTRIDGE15AMC",
        "AMC15EASTRIDGE",
        # Try some variations with numbers
        "EASTRIDGE1",
        "EASTRIDGE2", 
        "EASTRIDGE3",
        # Try some common AMC patterns
        "AADYN15",  # Based on Mercado pattern
        "EASTRIDGE_AADYN",
        "AADYN_EASTRIDGE",
    ]
    
    successful_ids = []
    
    for theater_id in possible_ids:
        print(f"\n🧪 Testing {theater_id}...")
        if test_theater_id(theater_id, "AMC Eastridge 15"):
            successful_ids.append(theater_id)
    
    if successful_ids:
        print(f"\n🎉 Found working IDs: {successful_ids}")
    else:
        print(f"\n😞 No working IDs found. You may need to:")
        print("1. Check Fandango website for the correct theater ID")
        print("2. Use browser developer tools to inspect the API calls")
        print("3. Try searching for the theater on Fandango directly")
    
    return successful_ids


def main():
    """Main function."""
    print("🎬 Fandango Theater ID Finder")
    print("=" * 40)
    
    if len(sys.argv) > 1:
        # Test specific ID provided by user
        theater_id = sys.argv[1]
        theater_name = sys.argv[2] if len(sys.argv) > 2 else "Test Theater"
        date_str = sys.argv[3] if len(sys.argv) > 3 else "2025-10-19"
        
        print(f"Testing specific ID: {theater_id}")
        test_theater_id(theater_id, theater_name, date_str)
    else:
        # Search for AMC Eastridge 15
        search_amc_eastridge()


if __name__ == "__main__":
    main()
