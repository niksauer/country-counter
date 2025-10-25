# Visited Countries Counter

This script counts the total number of unique countries visited based on a Google Takeout CSV export of saved places.

## Prerequisites

1. **Google Maps API Key**: You need a Google Maps API key with the Geocoding API enabled.
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the "Geocoding API"
   - Create credentials (API key)
   - Copy the API key

2. **CSV Export**: Export your "Visited" places from Google Takeout
   - Go to [Google Takeout](https://takeout.google.com/)
   - Select "Maps (your places)"
   - Export and download the data
   - Extract the `Visited.csv` file to the same directory as this script

## Usage

1. Set up your Google Maps API key:

```bash
# Create a .env file in the project root
echo "GOOGLE_MAPS_API_KEY=<snip>" > .env
```

2. Run the script:
   ```bash
   uv run scripts/count_visited_countries.py
   ```

## Features

- **Caching**: The script caches geocoding results in `cache.json` to avoid redundant API calls
- **Progress tracking**: Shows real-time progress as it processes locations
- **Interruptible**: You can interrupt (Ctrl+C) and resume later - progress is saved
- **Country statistics**: Shows total unique countries and location counts per country

## Output Example

```
Total unique countries visited: 15

Countries (with location counts):
  • United States of America: 234 locations
  • Deutschland: 89 locations
  • France: 45 locations
  ...
```

## Cost Considerations

The Google Maps Geocoding API has a cost associated with it:
- First $200/month is free (includes ~40,000 requests)
- After that, it's $5 per 1000 requests

With caching enabled, you'll only pay for new locations on subsequent runs.
