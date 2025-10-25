#!/usr/bin/env python3
"""
Script to count visited countries from Google Takeout "Visited" CSV export.
Uses Google Maps Geocoding API to determine countries from coordinates.
"""

import csv
import os
import re
import sys
from collections import Counter
from typing import Optional
from urllib.parse import unquote


def extract_place_id(url: str) -> Optional[str]:
    """
    Extract Google Place ID from Google Maps URL.

    Place IDs look like: 0x3e91f78734757c81:0xac41d82b1c3533f8
    """
    # Match the hex pattern in the URL
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1)
    return None


def extract_coordinates_from_url(url: str) -> Optional[tuple[float, float]]:
    """
    Extract latitude and longitude from Google Maps URL.

    Handles formats like:
    - https://www.google.com/maps/search/24.4840003,54.3536655
    """
    coord_match = re.search(r'/search/([-\d.]+),([-\d.]+)', url)
    if coord_match:
        try:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
            return (lat, lon)
        except ValueError:
            pass
    return None


def extract_place_name(title: str, url: str) -> str:
    """Extract a clean place name from title or URL."""
    if title and title.strip():
        return title.strip()

    # Extract from URL
    match = re.search(r'/place/([^/]+)/', url)
    if match:
        return unquote(match.group(1).replace('+', ' '))

    return ""


def get_country_from_coordinates(lat: float, lon: float, api_key: str, cache: dict) -> Optional[str]:
    """
    Get country from coordinates using Google Maps Geocoding API.
    """
    import urllib.request
    import urllib.parse
    import json
    import time

    # Check cache first
    cache_key = f"{lat:.6f},{lon:.6f}"
    if cache_key in cache:
        return cache[cache_key]

    # Google Maps Geocoding API
    params = urllib.parse.urlencode({
        'latlng': f"{lat},{lon}",
        'key': api_key,
        'result_type': 'country'
    })
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

            if data.get('status') == 'OK' and data.get('results'):
                # Extract country from the first result
                for component in data['results'][0].get('address_components', []):
                    if 'country' in component.get('types', []):
                        country = component.get('long_name')
                        cache[cache_key] = country
                        return country

        time.sleep(0.1)  # Small delay to respect API rate limits
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

    cache[cache_key] = None
    return None



def hex_to_cid(hex_place_id: str) -> Optional[str]:
    """
    Convert hex Place ID to Customer ID (CID).
    Based on Stack Overflow: https://stackoverflow.com/questions/44843934/get-lat-lon-from-google-maps-url-ftid-hex

    The second part of the hex ID (after colon) can be converted to decimal
    and used as a Customer ID with Google Maps Places API.
    """
    if ':' in hex_place_id:
        try:
            # Extract the second part after colon
            second_part = hex_place_id.split(':')[1]
            # Convert hex to decimal
            cid = str(int(second_part, 16))
            return cid
        except ValueError:
            pass
    return None


def get_country_from_hex_place_id(hex_place_id: str, api_key: str, cache: dict) -> Optional[str]:
    """
    Get country from hex Place ID by converting to Customer ID and using Places API.
    """
    import urllib.request
    import urllib.parse
    import json
    import time

    if not hex_place_id:
        return None

    # Check cache first
    cache_key = f"hex:{hex_place_id}"
    if cache_key in cache:
        return cache[cache_key]

    # Convert hex Place ID to Customer ID
    cid = hex_to_cid(hex_place_id)
    if not cid:
        cache[cache_key] = None
        return None

    # Use Places API with CID parameter
    params = urllib.parse.urlencode({
        'cid': cid,
        'key': api_key,
        'fields': 'name,formatted_address,address_components,geometry'
    })
    url = f"https://maps.googleapis.com/maps/api/place/details/json?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

            if data.get('status') == 'OK' and 'result' in data:
                result = data['result']

                # Extract country from address components
                if 'address_components' in result:
                    for component in result['address_components']:
                        if 'country' in component.get('types', []):
                            country = component.get('long_name')
                            cache[cache_key] = country
                            return country

        time.sleep(0.1)  # Small delay to respect API rate limits
    except Exception as e:
        print(f"Error resolving hex Place ID: {e}", file=sys.stderr)

    cache[cache_key] = None
    return None


def get_country_from_place_name(place_name: str, api_key: str, cache: dict) -> Optional[str]:
    """
    Get country from place name using Google Maps Geocoding API.
    """
    import urllib.request
    import urllib.parse
    import json
    import time

    if not place_name:
        return None

    # Check cache first
    if place_name in cache:
        return cache[place_name]

    # Google Maps Geocoding API
    params = urllib.parse.urlencode({
        'address': place_name,
        'key': api_key
    })
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

            if data.get('status') == 'OK' and data.get('results'):
                # Extract country from the first result
                for component in data['results'][0].get('address_components', []):
                    if 'country' in component.get('types', []):
                        country = component.get('long_name')
                        cache[place_name] = country
                        return country

        time.sleep(0.1)  # Small delay to respect API rate limits
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

    cache[place_name] = None
    return None


def load_cache(cache_file: str) -> dict:
    """Load geocoding cache from file."""
    import json

    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache: dict, cache_file: str):
    """Save geocoding cache to file."""
    import json

    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Could not save cache: {e}", file=sys.stderr)


def main():
    # Get API key from environment variable
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        print("Error: GOOGLE_MAPS_API_KEY environment variable not set", file=sys.stderr)
        print("\nUsage:", file=sys.stderr)
        print("  export GOOGLE_MAPS_API_KEY='your-api-key-here'", file=sys.stderr)
        print("  python3 count_visited_countries.py", file=sys.stderr)
        sys.exit(1)

    csv_file = 'Visited.csv'
    cache_file = 'cache.json'

    print(f"Reading {csv_file}...")

    # Load cache
    cache = load_cache(cache_file)
    print(f"Loaded {len(cache)} cached locations")

    countries = []
    failed_lookups = []

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total = len(rows)

            print(f"Found {total} locations. Starting geocoding with Google Maps API...\n")

            for idx, row in enumerate(rows, 1):
                title = row.get('Titel', '')
                url = row.get('URL', '')

                if not url:
                    continue

                print(f"[{idx}/{total}] Processing: {title or url[:50]}...",
                      end=' ',
                      flush=True)

                # Try to extract coordinates first (most reliable)
                coords = extract_coordinates_from_url(url)
                country = None

                if coords:
                    country = get_country_from_coordinates(*coords, api_key, cache)

                # If no coordinates, try hex Place ID (highly accurate)
                if not country:
                    hex_place_id = extract_place_id(url)
                    if hex_place_id:
                        country = get_country_from_hex_place_id(hex_place_id, api_key, cache)
                        if country:
                            print("🔍 Used hex Place ID")

                # If still no result, fall back to place name (least reliable)
                if not country:
                    place_name = extract_place_name(title, url)
                    if place_name:
                        # Check if URL has hex ID that might contradict the place name
                        has_hex_id = bool(re.search(r'1s0x[0-9a-fA-F]+:0x[0-9a-fA-F]+', url))
                        if has_hex_id:
                            print(f"⚠️ Place name '{place_name}' skipped (hex ID indicates potential mismatch)")
                        else:
                            country = get_country_from_place_name(place_name, api_key, cache)

                if country:
                    countries.append(country)
                    print(f"✓ {country}")
                else:
                    failed_lookups.append((title, url))
                    print("✗ Unable to determine country")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Saving progress...")
    finally:
        # Save cache even if interrupted
        print("\nSaving cache...")
        save_cache(cache, cache_file)

    # Count unique countries
    country_counts = Counter(countries)
    unique_countries = sorted(country_counts.keys())

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nTotal unique countries visited: {len(unique_countries)}\n")

    print("Countries (with location counts):")
    for country in unique_countries:
        count = country_counts[country]
        print(f"  • {country}: {count} location{'s' if count != 1 else ''}")

    if failed_lookups:
        print(
            f"\n⚠️  Failed to determine country for {len(failed_lookups)} location(s)"
        )
        print("These may need manual review.")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
