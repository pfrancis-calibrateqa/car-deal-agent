"""
used_car_values/fetch_car_values.py
=====================================
Fetches used car market values from dealer listings via the MarketCheck API 
and stores them in a local JSON cache file. Designed to be run on a schedule 
(e.g., nightly cron job) so that the application always reads from a fast 
local file rather than hitting the API on every request.

DATA SOURCE
-----------
MarketCheck API — https://www.marketcheck.com
  - Free tier: 500 calls/month, no credit card required
  - Sign up:   https://www.marketcheck.com/signup
  - Docs:      https://docs.marketcheck.com
  - Endpoint:  /v2/search/car/active (dealer listings)

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
  fetch_car_values.py  ──(API calls)──►  MarketCheck Dealer API
         │
         ▼
  car_values_cache.json   ◄──  your app reads this file (fast, offline)
  
NOTE: Cache contains dealer pricing. This provides a conservative baseline
      for evaluating private party deals found via scraping.
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

# Common trim levels by make/model
COMMON_TRIMS = {
    "Honda CR-V": ["LX", "EX", "EX-L", "Touring", "Sport"],
    "Mazda CX-5": ["Sport", "Touring", "Grand Touring", "Carbon", "Signature"],
}

def load_vehicles_from_config() -> list[dict]:
    """
    Reads config/search_criteria.json and generates a list of vehicles to fetch.
    For each make/model, fetches data for all specified years AND common trims.
    Now also fetches region-specific pricing for each configured region.
    """
    if not CONFIG_FILE.exists():
        log.error(f"Config file not found: {CONFIG_FILE}")
        return []
    
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    
    vehicles = []
    regions = config.get("regions", [])
    
    for search in config.get("searches", []):
        make = search["make"]
        model = search["model"]
        years = search["years"]
        
        # Get common trims for this make/model
        model_key = f"{make} {model}"
        trims = COMMON_TRIMS.get(model_key, [])
        
        # Fetch market data for each year, trim, and region combination
        for year in years:
            # For each region, fetch regional pricing
            for region in regions:
                region_name = region["name"]
                zip_code = region["center_zip"]
                radius = region["radius_miles"]
                
                # Generic data (all trims averaged) for this region
                vehicles.append({
                    "year": year,
                    "make": make,
                    "model": model,
                    "trim": None,
                    "region": region_name,
                    "zip_code": zip_code,
                    "radius": radius
                })
                
                # Trim-specific data for this region
                for trim in trims:
                    vehicles.append({
                        "year": year,
                        "make": make,
                        "model": model,
                        "trim": trim,
                        "region": region_name,
                        "zip_code": zip_code,
                        "radius": radius
                    })
    
    log.info(f"Loaded {len(vehicles)} vehicle configurations from {CONFIG_FILE}")
    log.info(f"  (includes {len(regions)} regions × generic + trim-specific data)")
    return vehicles


# ── API Helpers ───────────────────────────────────────────────────────────────

def get_market_stats(year: int, make: str, model: str, trim: str = None,
                     zip_code: str = None, radius: int = 100) -> dict | None:
    """
    Calls MarketCheck's dealer inventory search with stats=true to get aggregated
    pricing (avg, min, max price and mileage) for a specific used vehicle.
    
    Now supports regional pricing via zip_code and radius parameters.

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
    if zip_code:
        params["zip"] = zip_code
        params["radius"] = radius

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
            region_label = f" (ZIP {zip_code}, {radius}mi)" if zip_code else ""
            log.warning(f"  No listings found for {year} {make} {model} {trim or ''}{region_label}")
            return None

        return {
            "listings_count":   count,
            "price_avg":        round(price_stats.get("mean") or 0),
            "price_min":        round(price_stats.get("min") or 0),
            "price_max":        round(price_stats.get("max") or 0),
            "price_median":     round(price_stats.get("median") or 0),
            "mileage_avg":      round(miles_stats.get("mean") or 0),
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
        region = vehicle.get("region")
        zip_code = vehicle.get("zip_code")
        radius = vehicle.get("radius", 100)

        label = f"{year} {make} {model} {trim or '(all trims)'}".strip()
        region_label = f" [{region}]" if region else ""
        log.info(f"  Fetching: {label}{region_label}")

        stats = get_market_stats(year, make, model, trim, zip_code, radius)

        record = {
            "year":  year,
            "make":  make,
            "model": model,
            "trim":  trim,
            "region": region,
            "zip_code": zip_code,
            "radius": radius,
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
            "seller_type":  "dealer",
            "config_file":  str(CONFIG_FILE),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "vehicles_requested": len(VEHICLES_TO_TRACK),
            "vehicles_with_data": success_count,
            "notes": (
                "Prices from dealer listings (not private party). "
                "Regional pricing enabled: data fetched for each configured region with ZIP+radius. "
                "MarketCheck free tier: 500 calls/month. Refresh this file daily or weekly. "
                "Vehicle list automatically synced from search_criteria.json. "
                "Dealer pricing provides a conservative baseline for evaluating private party deals."
            ),
        },
        "vehicles": results,
    }

    # Write to disk
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    # Create timestamped backup
    backup_dir = CACHE_FILE.parent / "cache_backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"car_values_cache_{timestamp}.json"
    with open(backup_file, "w") as f:
        json.dump(cache, f, indent=2)

    log.info("=" * 60)
    log.info(f"Done. {success_count}/{len(VEHICLES_TO_TRACK)} vehicles fetched successfully.")
    log.info(f"Cache written to: {CACHE_FILE}")
    log.info(f"Backup created: {backup_file}")
    log.info("=" * 60)
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
