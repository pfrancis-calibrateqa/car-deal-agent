"""
used_car_values/fetch_car_values.py
=====================================
Fetches used car market values from the MarketCheck API and stores them
in a local JSON cache file. Designed to be run on a schedule (e.g., nightly
cron job) so that the application always reads from a fast local file rather
than hitting the API on every request.

DATA SOURCE
-----------
MarketCheck API — https://www.marketcheck.com
  - Free tier: 500 calls/month, no credit card required
  - Sign up:   https://www.marketcheck.com/signup
  - Docs:      https://docs.marketcheck.com

SETUP
-----
1. Sign up at marketcheck.com and get a free API key
2. Add to .env:  MARKETCHECK_API_KEY="your_key_here"
                 MARKETCHECK_SECRET="your_secret_here"
3. Install deps:  pip install requests
4. Run manually:  python fetch_car_values.py
5. Schedule it:   crontab -e  →  0 2 * * * python /path/to/fetch_car_values.py

HOW IT WORKS
------------
  fetch_car_values.py  ──(API calls)──►  MarketCheck API
         │
         ▼
  car_values_cache.json   ◄──  your app reads this file (fast, offline)
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

API_KEY       = os.environ.get("MARKETCHECK_API_KEY", "YOUR_API_KEY_HERE")
API_SECRET    = os.environ.get("MARKETCHECK_SECRET", "YOUR_SECRET_HERE")
BASE_URL      = "https://api.marketcheck.com/v2"
ROOT          = Path(__file__).parent.parent
CACHE_FILE    = Path(__file__).parent / "car_values_cache.json"
CONFIG_FILE   = ROOT / "config" / "search_criteria.json"
REQUEST_DELAY = 0.5   # seconds between API calls (respect rate limits: 5/sec on free tier)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Load vehicles from search_criteria.json ───────────────────────────────────

def load_vehicles_from_config() -> list[dict]:
    """
    Reads config/search_criteria.json and generates a list of vehicles to fetch.
    For each make/model, fetches data for all specified years.
    """
    if not CONFIG_FILE.exists():
        log.error(f"Config file not found: {CONFIG_FILE}")
        return []
    
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    
    vehicles = []
    for search in config.get("searches", []):
        make = search["make"]
        model = search["model"]
        years = search["years"]
        
        # Fetch market data for each year
        for year in years:
            vehicles.append({
                "year": year,
                "make": make,
                "model": model,
                "trim": None  # We'll fetch aggregate data across all trims
            })
    
    log.info(f"Loaded {len(vehicles)} vehicle configurations from {CONFIG_FILE}")
    return vehicles


# ── API Helpers ───────────────────────────────────────────────────────────────

def get_market_stats(year: int, make: str, model: str, trim: str = None) -> dict | None:
    """
    Calls MarketCheck's inventory search with stats=true to get aggregated
    pricing (avg, min, max price and mileage) for a specific used vehicle.

    Endpoint: GET /v2/search/car/active
    Docs: https://docs.marketcheck.com/docs/api/cars/inventory/active-inventory-search
    """
    params = {
        "api_key":  API_KEY,
        "car_type": "used",
        "year":     year,
        "make":     make,
        "model":    model,
        "stats":    "price,miles",   # request aggregated stats in the response
        "rows":     0,               # we only want stats, not individual listings
    }
    if trim:
        params["trim"] = trim

    try:
        resp = requests.get(
            f"{BASE_URL}/search/car/active",
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        # MarketCheck returns stats under data["stats"] when stats param is set
        stats = data.get("stats", {})
        price_stats = stats.get("price", {})
        miles_stats = stats.get("miles", {})
        count = data.get("totalListings", data.get("num_found", 0))

        if not price_stats or count == 0:
            log.warning(f"  No listings found for {year} {make} {model} {trim or ''}")
            return None

        return {
            "listings_count":   count,
            "price_avg":        round(price_stats.get("mean", 0)),
            "price_min":        round(price_stats.get("min", 0)),
            "price_max":        round(price_stats.get("max", 0)),
            "price_median":     round(price_stats.get("median", 0)),
            "mileage_avg":      round(miles_stats.get("mean", 0)),
        }

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            log.error("  ✗ Invalid API key. Check your MARKETCHECK_API_KEY environment variable.")
        elif e.response.status_code == 429:
            log.warning("  ✗ Rate limit hit — sleeping 10 seconds before retry...")
            time.sleep(10)
        else:
            log.error(f"  ✗ HTTP {e.response.status_code}: {e}")
        return None

    except requests.exceptions.RequestException as e:
        log.error(f"  ✗ Network error: {e}")
        return None


# ── Main Fetch & Cache Logic ──────────────────────────────────────────────────

def fetch_and_cache():
    """
    Main function. Loads vehicles from search_criteria.json, fetches pricing
    stats from MarketCheck, and writes the result to car_values_cache.json.
    """
    log.info("=" * 60)
    log.info("Starting used car value fetch...")
    log.info(f"Config file: {CONFIG_FILE}")
    log.info(f"Cache file: {CACHE_FILE}")
    log.info("=" * 60)

    VEHICLES_TO_TRACK = load_vehicles_from_config()
    
    if not VEHICLES_TO_TRACK:
        log.error("No vehicles found in config. Exiting.")
        return
    
    log.info(f"Target vehicles: {len(VEHICLES_TO_TRACK)}")
    log.info("=" * 60)

    results = []
    success_count = 0

    for vehicle in VEHICLES_TO_TRACK:
        year  = vehicle["year"]
        make  = vehicle["make"]
        model = vehicle["model"]
        trim  = vehicle.get("trim")

        label = f"{year} {make} {model} {trim or '(all trims)'}".strip()
        log.info(f"  Fetching: {label}")

        stats = get_market_stats(year, make, model, trim)

        record = {
            "year":  year,
            "make":  make,
            "model": model,
            "trim":  trim,
        }

        if stats:
            record.update(stats)
            record["fetch_status"] = "success"
            success_count += 1
            log.info(
                f"    ✓ avg=${stats['price_avg']:,}  "
                f"range=${stats['price_min']:,}–${stats['price_max']:,}  "
                f"({stats['listings_count']} listings)"
            )
        else:
            record["fetch_status"] = "no_data"
            log.warning(f"    ✗ No data returned")

        results.append(record)
        time.sleep(REQUEST_DELAY)

    # Build the final cache payload
    cache = {
        "metadata": {
            "source":       "MarketCheck API (https://www.marketcheck.com)",
            "endpoint":     f"{BASE_URL}/search/car/active",
            "config_file":  str(CONFIG_FILE),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "vehicles_requested": len(VEHICLES_TO_TRACK),
            "vehicles_with_data": success_count,
            "notes": (
                "Prices are averages across active used-car listings nationwide. "
                "MarketCheck free tier: 500 calls/month. Refresh this file daily or weekly. "
                "Vehicle list automatically synced from search_criteria.json."
            ),
        },
        "vehicles": results,
    }

    # Write to disk
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    log.info("=" * 60)
    log.info(f"Done. {success_count}/{len(VEHICLES_TO_TRACK)} vehicles fetched successfully.")
    log.info(f"Cache written to: {CACHE_FILE}")
    log.info("=" * 60)


if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY_HERE":
        log.error(
            "No API key set!\n"
            "  1. Sign up free at https://www.marketcheck.com/signup\n"
            "  2. Run: export MARKETCHECK_API_KEY='your_key_here'\n"
            "  3. Then re-run this script."
        )
    else:
        fetch_and_cache()
