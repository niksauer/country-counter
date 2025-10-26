#!/usr/bin/env python3
"""
Script to count countries from Google Takeout CSV export.
Uses Google Maps Geocoding API to determine countries from coordinates.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
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


CACHE_SCHEMA_VERSION = 3


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


def load_cache(shared_cache_file: str, place_name_cache_file: str) -> tuple[dict, dict]:
    """
    Load geocoding cache from split cache files.

    Returns:
        tuple: (shared_cache, place_name_cache)
        - shared_cache: hex Place IDs and coordinates (shared across all input files)
        - place_name_cache: place names (isolated per input file)
    """
    shared_cache = {}
    place_name_cache = {}

    # Check for old monolithic cache file for migration
    old_cache_file = place_name_cache_file.replace('_place_names.json', '.json')
    if os.path.exists(old_cache_file) and not old_cache_file.endswith(
        '_place_names.json'
    ):
        # This is an old v1 or v2 cache that needs migration
        print(f'Migrating old cache file: {old_cache_file}')
        with open(old_cache_file, encoding='utf-8') as f:
            old_cache_data = json.load(f)

        # Migrate to v3 format
        shared_cache_new, place_name_cache_new = migrate_cache_to_v3(old_cache_data)

        # Load existing shared cache if it exists
        if os.path.exists(shared_cache_file):
            with open(shared_cache_file, encoding='utf-8') as f:
                existing_shared = json.load(f)
                # Remove schema_version key for compatibility
                shared_cache = {
                    k: v for k, v in existing_shared.items() if k != 'schema_version'
                }

        # Merge migrated shared cache into existing
        shared_cache.update(shared_cache_new)
        place_name_cache = place_name_cache_new

        # Save the split caches
        save_cache(
            shared_cache, place_name_cache, shared_cache_file, place_name_cache_file
        )

        # Rename old cache file
        os.rename(old_cache_file, old_cache_file + '.v2.bak')
        print(f'Migrated and backed up old cache to: {old_cache_file}.v2.bak')

        return shared_cache, place_name_cache

    # Load shared cache (hex IDs and coordinates)
    if os.path.exists(shared_cache_file):
        with open(shared_cache_file, encoding='utf-8') as f:
            shared_data = json.load(f)
            # Remove schema_version key for compatibility
            shared_cache = {k: v for k, v in shared_data.items() if k != 'schema_version'}

    # Load place name cache (per-file)
    if os.path.exists(place_name_cache_file):
        with open(place_name_cache_file, encoding='utf-8') as f:
            place_data = json.load(f)
            # Remove schema_version key for compatibility
            place_name_cache = {
                k: v for k, v in place_data.items() if k != 'schema_version'
            }

    return shared_cache, place_name_cache


def migrate_cache_to_v3(old_cache_data: dict) -> tuple[dict, dict]:
    """
    Migrate v1/v2 cache to v3 format by splitting into shared and place-name caches.

    Returns:
        tuple: (shared_cache, place_name_cache)
    """
    # First do v1->v2 migration if needed
    if old_cache_data.get('schema_version', 1) < 2:
        old_cache_data = {'schema_version': 2, **migrate_cache_once(old_cache_data)}

    shared_cache = {}
    place_name_cache = {}

    # Remove schema_version from old data
    cache_entries = {k: v for k, v in old_cache_data.items() if k != 'schema_version'}

    for key, value in cache_entries.items():
        # Hex Place IDs and coordinates go to shared cache
        if key.startswith('hex:') or re.match(r'^-?\d+\.\d+,-?\d+\.\d+$', key):
            shared_cache[key] = value
        else:
            # Place names go to per-file cache
            place_name_cache[key] = value

    print(
        f'Split cache: {len(shared_cache)} shared entries, {len(place_name_cache)} place name entries'
    )
    return shared_cache, place_name_cache


def save_cache(
    shared_cache: dict,
    place_name_cache: dict,
    shared_cache_file: str,
    place_name_cache_file: str,
):
    """Save geocoding caches to split cache files with schema version."""
    # Save shared cache (hex and coordinates)
    shared_with_schema = {'schema_version': CACHE_SCHEMA_VERSION}
    shared_with_schema.update(shared_cache)
    with open(shared_cache_file, 'w', encoding='utf-8') as f:
        json.dump(shared_with_schema, f, ensure_ascii=False, indent=2)

    # Save place name cache (per-file)
    place_with_schema = {'schema_version': CACHE_SCHEMA_VERSION}
    place_with_schema.update(place_name_cache)
    with open(place_name_cache_file, 'w', encoding='utf-8') as f:
        json.dump(place_with_schema, f, ensure_ascii=False, indent=2)


def save_failed_lookups(failed_lookups: list, failed_lookups_file: str):
    """Save failed lookups to a separate JSON file for manual review."""
    failed_data = {
        'schema_version': 1,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_failed': len(failed_lookups),
        'failed_locations': [
            {
                'title': title,
                'url': url,
                'reason': 'Unable to determine country from coordinates, hex Place ID, or place name',
            }
            for title, url in failed_lookups
        ],
    }

    with open(failed_lookups_file, 'w', encoding='utf-8') as f:
        json.dump(failed_data, f, ensure_ascii=False, indent=2)


def save_countries_json(country_states_map: dict, output_file: str):
    """
    Save countries and their states to a JSON file.

    Output format: [{"country": "Country Name", "count": 123, "states": ["State1", "State2"]}, ...]
    States are sorted alphabetically. Countries with no states have an empty array.
    """
    output_data = []

    for country in sorted(country_states_map.keys()):
        data = country_states_map[country]
        states = sorted(data['states'])
        output_data.append({'country': country, 'count': data['count'], 'states': states})

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Count countries from Google Takeout CSV export'
    )
    parser.add_argument('csv_file', help='Path to the CSV file to process')
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show live processing output (default is silent mode)',
    )
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()

    # Get API key from environment variable
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        print('Error: GOOGLE_MAPS_API_KEY not found', file=sys.stderr)
        sys.exit(1)

    # Get CSV file from command line argument
    csv_file = args.csv_file

    # Check if CSV file exists
    if not os.path.exists(csv_file):
        print(f'Error: CSV file "{csv_file}" not found', file=sys.stderr)
        sys.exit(1)

    # Generate cache file names based on CSV filename
    csv_basename = os.path.splitext(os.path.basename(csv_file))[0]
    cache_dir = 'cache'

    # Create cache directory if it doesn't exist
    os.makedirs(cache_dir, exist_ok=True)

    # v3 uses split caches: shared for hex/coord, per-file for place names
    shared_cache_file = os.path.join(cache_dir, 'shared_hex_coord_cache.json')
    place_name_cache_file = os.path.join(cache_dir, f'{csv_basename}_place_names.json')
    failed_lookups_file = os.path.join(cache_dir, f'{csv_basename}_failed_lookups.json')
    countries_json_file = os.path.join(cache_dir, f'{csv_basename}_countries.json')

    if args.verbose:
        print(f'Reading {csv_file}...')

    # Load split caches
    shared_cache, place_name_cache = load_cache(shared_cache_file, place_name_cache_file)
    if args.verbose:
        print(
            f'Loaded {len(shared_cache)} shared cached locations and {len(place_name_cache)} place name cached locations'
        )

    # Track states and counts per country: {country: {'states': set(states), 'count': int}}
    country_states_map = {}
    failed_lookups = []

    try:
        with open(csv_file, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total = len(rows)

            if args.verbose:
                print(
                    f'Found {total} locations. Starting geocoding with Google Maps API...\n'
                )

            for idx, row in enumerate(rows, 1):
                title = row.get('Titel', '')
                url = row.get('URL', '')

                if not url:
                    continue

                if args.verbose:
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
                        *coords, api_key, shared_cache
                    )

                # If no coordinates, try hex Place ID (highly accurate)
                if not country:
                    hex_place_id = extract_place_id(url)
                    if hex_place_id:
                        country, state = get_location_info_from_hex_place_id(
                            hex_place_id, api_key, shared_cache
                        )
                        if country and args.verbose:
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
                            if args.verbose:
                                print(
                                    f"⚠️ Place name '{place_name}' skipped (hex ID indicates potential mismatch)"
                                )
                        else:
                            country, state = get_location_info_from_place_name(
                                place_name, api_key, place_name_cache
                            )

                if country:
                    # Track states and counts per country
                    if country not in country_states_map:
                        country_states_map[country] = {'states': set(), 'count': 0}

                    country_states_map[country]['count'] += 1

                    if state:
                        country_states_map[country]['states'].add(state)

                    # Print progress
                    if args.verbose:
                        if state:
                            print(f'✓ {country} ({state})')
                        else:
                            print(f'✓ {country}')
                else:
                    failed_lookups.append((title, url))
                    if args.verbose:
                        print('✗ Unable to determine country')
    except KeyboardInterrupt:
        if args.verbose:
            print('\n\nInterrupted by user. Saving progress...')
    finally:
        # Save cache even if interrupted
        if args.verbose:
            print('\nSaving cache...')
        save_cache(
            shared_cache, place_name_cache, shared_cache_file, place_name_cache_file
        )

        # Save failed lookups for manual review
        if failed_lookups:
            save_failed_lookups(failed_lookups, failed_lookups_file)
            if args.verbose:
                print(
                    f'Saved {len(failed_lookups)} failed lookups to {failed_lookups_file}'
                )

    # Save countries and states to JSON file
    save_countries_json(country_states_map, countries_json_file)
    if args.verbose:
        print(f'\nSaved countries and states to {countries_json_file}')

    print('\n' + '=' * 70)
    print('RESULTS')
    print('=' * 70)
    print(f'\nTotal unique countries: {len(country_states_map)}')

    # Count total unique states across all countries
    total_unique_states = sum(len(data['states']) for data in country_states_map.values())
    if total_unique_states > 0:
        print(f'Total unique states across all countries: {total_unique_states}')
    print()

    print('Countries (with location counts and states):')
    for country in sorted(country_states_map.keys()):
        data = country_states_map[country]
        count = data['count']
        states = sorted(data['states'])

        if states:
            print(f'  • {country}: {count} location{"s" if count != 1 else ""}')
            for state in states:
                print(f'    - {state}')
        else:
            print(f'  • {country}: {count} location{"s" if count != 1 else ""}')

    if failed_lookups:
        print(f'\n⚠️  Failed to lookup {len(failed_lookups)} location(s)')
        print('These may need manual review. See failed_lookups.json for details.')

    print('\n' + '=' * 70)


if __name__ == '__main__':
    main()
