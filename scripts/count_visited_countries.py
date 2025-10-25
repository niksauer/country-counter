#!/usr/bin/env python3
"""
Script to count visited countries from Google Takeout "Visited" CSV export.
Uses Google Maps Geocoding API to determine countries from coordinates.
"""

import csv
import json
import os
import re
import sys
import time
from collections import Counter
from urllib.parse import unquote

import requests
from dotenv import load_dotenv


def extract_place_id(url: str) -> str | None:
    """
    Extract Google Place ID from Google Maps URL.

    Place IDs look like: 0x3e91f78734757c81:0xac41d82b1c3533f8
    """
    # Match the hex pattern in the URL
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1)
    return None


def extract_coordinates_from_url(url: str) -> tuple[float, float] | None:
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

    return ''


def get_location_info_from_coordinates(
    lat: float, lon: float, api_key: str, cache: dict
) -> tuple[str | None, str | None]:
    """
    Get country and state (if US) from coordinates using Google Maps Geocoding API.
    Returns (country, state) tuple.
    """

    # Check cache first
    cache_key = f'{lat:.6f},{lon:.6f}'
    if cache_key in cache:
        cached = cache[cache_key]
        # Always expect new format: {'country': 'Country', 'state': 'State'}
        return cached.get('country'), cached.get('state')

    # Google Maps Geocoding API (remove result_type to get full address components)
    params = {'latlng': f'{lat},{lon}', 'key': api_key}
    url = 'https://maps.googleapis.com/maps/api/geocode/json'

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('status') == 'OK' and data.get('results'):
            country = None
            state = None

            # Extract country and state from the first result
            for component in data['results'][0].get('address_components', []):
                types = component.get('types', [])
                if 'country' in types:
                    country = component.get('long_name')
                elif 'administrative_area_level_1' in types:
                    state = component.get('long_name')

            # Cache the result
            result = {'country': country, 'state': state}
            cache[cache_key] = result
            return country, state

        time.sleep(0.1)  # Small delay to respect API rate limits
    except requests.RequestException as e:
        print(f'Error: {e}', file=sys.stderr)

    cache[cache_key] = {'country': None, 'state': None}
    return None, None


def hex_to_cid(hex_place_id: str) -> str | None:
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
            return str(int(second_part, 16))
        except ValueError:
            pass
    return None


def get_location_info_from_hex_place_id(
    hex_place_id: str, api_key: str, cache: dict
) -> tuple[str | None, str | None]:
    """
    Get country and state (if US) from hex Place ID by converting to Customer ID and using Places API.
    Returns (country, state) tuple.
    """

    if not hex_place_id:
        return None, None

    # Check cache first
    cache_key = f'hex:{hex_place_id}'
    if cache_key in cache:
        cached = cache[cache_key]
        # Always expect new format: {'country': 'Country', 'state': 'State'}
        return cached.get('country'), cached.get('state')

    # Convert hex Place ID to Customer ID
    cid = hex_to_cid(hex_place_id)
    if not cid:
        cache[cache_key] = {'country': None, 'state': None}
        return None, None

    # Use Places API with CID parameter
    params = {
        'cid': cid,
        'key': api_key,
        'fields': 'name,formatted_address,address_components,geometry',
    }
    url = 'https://maps.googleapis.com/maps/api/place/details/json'

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('status') == 'OK' and 'result' in data:
            result = data['result']
            country = None
            state = None

            # Extract country and state from address components
            if 'address_components' in result:
                for component in result['address_components']:
                    types = component.get('types', [])
                    if 'country' in types:
                        country = component.get('long_name')
                    elif 'administrative_area_level_1' in types:
                        state = component.get('long_name')

            # Cache the result
            result_data = {'country': country, 'state': state}
            cache[cache_key] = result_data
            return country, state

        time.sleep(0.1)  # Small delay to respect API rate limits
    except requests.RequestException as e:
        print(f'Error resolving hex Place ID: {e}', file=sys.stderr)

    cache[cache_key] = {'country': None, 'state': None}
    return None, None


def get_location_info_from_place_name(
    place_name: str, api_key: str, cache: dict
) -> tuple[str | None, str | None]:
    """
    Get country and state (if US) from place name using Google Maps Geocoding API.
    Returns (country, state) tuple.
    """

    if not place_name:
        return None, None

    # Check cache first
    if place_name in cache:
        cached = cache[place_name]
        # Always expect new format: {'country': 'Country', 'state': 'State'}
        return cached.get('country'), cached.get('state')

    # Google Maps Geocoding API
    params = {'address': place_name, 'key': api_key}
    url = 'https://maps.googleapis.com/maps/api/geocode/json'

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('status') == 'OK' and data.get('results'):
            country = None
            state = None

            # Extract country and state from the first result
            for component in data['results'][0].get('address_components', []):
                types = component.get('types', [])
                if 'country' in types:
                    country = component.get('long_name')
                elif 'administrative_area_level_1' in types:
                    state = component.get('long_name')

            # Cache the result
            result = {'country': country, 'state': state}
            cache[place_name] = result
            return country, state

        time.sleep(0.1)  # Small delay to respect API rate limits
    except requests.RequestException as e:
        print(f'Error: {e}', file=sys.stderr)

    cache[place_name] = {'country': None, 'state': None}
    return None, None


CACHE_SCHEMA_VERSION = 2


def migrate_cache_once(cache_data: dict) -> dict:
    """
    One-time migration from old cache format to new format with schema versioning.
    Only runs if schema_version is missing or outdated.
    """
    current_version = cache_data.get('schema_version', 1)

    if current_version >= CACHE_SCHEMA_VERSION:
        # Already at latest version - return without schema_version key
        return {k: v for k, v in cache_data.items() if k != 'schema_version'}

    print(
        f'Migrating cache from schema version {current_version} to {CACHE_SCHEMA_VERSION}...'
    )

    # Extract the actual cache entries (excluding metadata)
    cache_entries = {k: v for k, v in cache_data.items() if k != 'schema_version'}

    migrated_cache: dict = {}
    migrated_count = 0
    removed_us_count = 0

    for key, value in cache_entries.items():
        if isinstance(value, str):
            # Old format - migrate to new format
            if value == 'United States':
                # Remove US entries so they get re-fetched with state info
                removed_us_count += 1
                continue
            # Migrate non-US entries to new format
            migrated_cache[key] = {'country': value, 'state': None}
            migrated_count += 1
        elif isinstance(value, dict):
            # Already in new format - keep as is
            migrated_cache[key] = value
        elif value is None:
            # Keep None values (failed lookups)
            migrated_cache[key] = {'country': None, 'state': None}

    print(
        f'Cache migration complete: {migrated_count} entries migrated, {removed_us_count} US entries removed for re-fetching'
    )
    return migrated_cache


def load_cache(cache_file: str) -> dict:
    """Load geocoding cache from file with schema versioning."""
    if os.path.exists(cache_file):
        with open(cache_file, encoding='utf-8') as f:
            cache_data = json.load(f)

        # Check if migration is needed
        if cache_data.get('schema_version', 1) < CACHE_SCHEMA_VERSION:
            migrated_cache = migrate_cache_once(cache_data)
            # Save the migrated cache immediately
            save_cache(migrated_cache, cache_file)
            return migrated_cache

        # Return cache without schema_version key for compatibility
        return {k: v for k, v in cache_data.items() if k != 'schema_version'}

    return {}


def save_cache(cache: dict, cache_file: str):
    """Save geocoding cache to file with schema version."""
    cache_with_schema = {'schema_version': CACHE_SCHEMA_VERSION}
    cache_with_schema.update(cache)

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_with_schema, f, ensure_ascii=False, indent=2)


def main():
    # Load environment variables from .env file
    load_dotenv()

    # Get API key from environment variable
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        print('Error: GOOGLE_MAPS_API_KEY not found', file=sys.stderr)
        sys.exit(1)

    csv_file = 'Visited.csv'
    cache_file = 'cache.json'

    print(f'Reading {csv_file}...')

    # Load cache
    cache = load_cache(cache_file)
    print(f'Loaded {len(cache)} cached locations')

    countries = []
    us_states = []  # Track US states separately
    failed_lookups = []

    try:
        with open(csv_file, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total = len(rows)

            print(
                f'Found {total} locations. Starting geocoding with Google Maps API...\n'
            )

            for idx, row in enumerate(rows, 1):
                title = row.get('Titel', '')
                url = row.get('URL', '')

                if not url:
                    continue

                print(
                    f'[{idx}/{total}] Processing: {title or url[:50]}...',
                    end=' ',
                    flush=True,
                )

                # Try to extract coordinates first (most reliable)
                coords = extract_coordinates_from_url(url)
                country = None
                state = None

                if coords:
                    country, state = get_location_info_from_coordinates(
                        *coords, api_key, cache
                    )

                # If no coordinates, try hex Place ID (highly accurate)
                if not country:
                    hex_place_id = extract_place_id(url)
                    if hex_place_id:
                        country, state = get_location_info_from_hex_place_id(
                            hex_place_id, api_key, cache
                        )
                        if country:
                            print('🔍 Used hex Place ID')

                # If still no result, fall back to place name (least reliable)
                if not country:
                    place_name = extract_place_name(title, url)
                    if place_name:
                        # Check if URL has hex ID that might contradict the place name
                        has_hex_id = bool(
                            re.search(r'1s0x[0-9a-fA-F]+:0x[0-9a-fA-F]+', url)
                        )
                        if has_hex_id:
                            print(
                                f"⚠️ Place name '{place_name}' skipped (hex ID indicates potential mismatch)"
                            )
                        else:
                            country, state = get_location_info_from_place_name(
                                place_name, api_key, cache
                            )

                if country:
                    countries.append(country)
                    # Track US states
                    if country == 'United States' and state:
                        us_states.append(state)
                        print(f'✓ {country} ({state})')
                    else:
                        print(f'✓ {country}')
                else:
                    failed_lookups.append((title, url))
                    print('✗ Unable to determine country')
    except KeyboardInterrupt:
        print('\n\nInterrupted by user. Saving progress...')
    finally:
        # Save cache even if interrupted
        print('\nSaving cache...')
        save_cache(cache, cache_file)

    # Count unique countries and US states
    country_counts = Counter(countries)
    us_state_counts = Counter(us_states)
    unique_countries = sorted(country_counts.keys())
    unique_us_states = sorted(us_state_counts.keys()) if us_states else []

    print('\n' + '=' * 70)
    print('RESULTS')
    print('=' * 70)
    print(f'\nTotal unique countries visited: {len(unique_countries)}')
    if unique_us_states:
        print(f'Total unique US states visited: {len(unique_us_states)}')
    print()

    print('Countries (with location counts):')
    for country in unique_countries:
        count = country_counts[country]
        print(f'  • {country}: {count} location{"s" if count != 1 else ""}')

    if unique_us_states:
        print('\nUS States (with location counts):')
        for state in unique_us_states:
            count = us_state_counts[state]
            print(f'  • {state}: {count} location{"s" if count != 1 else ""}')

    if failed_lookups:
        print(f'\n⚠️  Failed to determine country for {len(failed_lookups)} location(s)')
        print('These may need manual review.')

    print('\n' + '=' * 70)


if __name__ == '__main__':
    main()
