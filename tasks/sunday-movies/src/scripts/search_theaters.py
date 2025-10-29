#!/usr/bin/env python3
"""Script to search for theaters on Fandango."""

import requests
import json
import sys
from pathlib import Path

def search_theaters_by_location(location: str = "San Jose, CA") -> list:
    """Search for theaters by location."""
    print(f"🔍 Searching for theaters near {location}...")
    
    # Fandango theater search endpoint
    search_url = "https://www.fandango.com/napi/search/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.fandango.com/",
    }
    
    try:
        # Search for theaters
        response = requests.get(
            search_url,
            params={"query": location, "type": "theater"},
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        
        data = response.json()
        theaters = data.get("theaters", [])
        
        print(f"Found {len(theaters)} theaters:")
        
        amc_theaters = []
        for theater in theaters:
            name = theater.get("name", "")
            theater_id = theater.get("id", "")
            address = theater.get("address", "")
            
            print(f"   - {name} (ID: {theater_id})")
            if address:
                print(f"     Address: {address}")
            
            # Look for AMC Eastridge specifically
            if "eastridge" in name.lower() or "15" in name.lower():
                amc_theaters.append((theater_id, name))
                print(f"     🎯 Potential match for AMC Eastridge!")
        
        return amc_theaters
        
    except Exception as e:
        print(f"❌ Error searching theaters: {e}")
        return []


def search_theaters_by_name(theater_name: str) -> list:
    """Search for theaters by name."""
    print(f"🔍 Searching for theaters with name: {theater_name}...")
    
    search_url = "https://www.fandango.com/napi/search/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.fandango.com/",
    }
    
    try:
        response = requests.get(
            search_url,
            params={"query": theater_name, "type": "theater"},
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        
        data = response.json()
        theaters = data.get("theaters", [])
        
        print(f"Found {len(theaters)} theaters matching '{theater_name}':")
        
        matches = []
        for theater in theaters:
            name = theater.get("name", "")
            theater_id = theater.get("id", "")
            address = theater.get("address", "")
            
            print(f"   - {name} (ID: {theater_id})")
            if address:
                print(f"     Address: {address}")
            
            matches.append((theater_id, name))
        
        return matches
        
    except Exception as e:
        print(f"❌ Error searching theaters: {e}")
        return []


def main():
    """Main function."""
    print("🎬 Fandango Theater Search Tool")
    print("=" * 40)
    
    # Search by location first
    location_matches = search_theaters_by_location("San Jose, CA")
    
    print("\n" + "=" * 40)
    
    # Search by specific name
    name_matches = search_theaters_by_name("AMC Eastridge")
    
    print("\n" + "=" * 40)
    
    # Search for any AMC theaters
    amc_matches = search_theaters_by_name("AMC")
    
    # Combine and deduplicate results
    all_matches = list(set(location_matches + name_matches + amc_matches))
    
    if all_matches:
        print(f"\n🎯 Found {len(all_matches)} potential AMC Eastridge theaters:")
        for theater_id, name in all_matches:
            print(f"   - {theater_id}: {name}")
        
        print(f"\n💡 To test a specific theater ID, run:")
        print(f"   python tasks/sunday-movies/src/scripts/find_theater_id.py <THEATER_ID>")
    else:
        print(f"\n😞 No AMC Eastridge theaters found.")
        print(f"💡 Try searching manually on Fandango.com")


if __name__ == "__main__":
    main()
