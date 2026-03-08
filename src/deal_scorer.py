"""
deal_scorer.py
==============
Core engine. Takes a scraped car listing and compares it against market
values from the cache (or a live API call on cache miss). Returns a
structured result with both a deal score and raw numbers.

                  Scraped Listing
                       │
                       ▼
              ┌─────────────────┐
              │   DealScorer    │
              │                 │
              │  1. Normalize   │  ← clean up scraped fields
              │  2. Cache Lookup│  ← fast path (JSON file)
              │  3. API Fallback│  ← on cache miss (burns quota)
              │  4. Mileage Adj │  ← adjust for high/low miles
              │  5. Score       │  ← % below/above market
              └─────────────────┘
                       │
                       ▼
                 DealResult
           {score, grade, savings,
            asking, market_avg, ...}
"""

import os
import json
import time
import logging
import requests
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

API_KEY    = os.environ.get("MARKETCHECK_API_KEY", "")
API_SECRET = os.environ.get("MARKETCHECK_SECRET", "")
BASE_URL   = "https://api.marketcheck.com/v2"
CACHE_FILE = Path(__file__).parent / "car_values_cache.json"

# Mileage adjustment: for every 1,000 miles above/below the market average,
# adjust the fair value by this dollar amount (rough industry heuristic: ~$0.05/mile)
MILEAGE_ADJUSTMENT_PER_1K = 50   # $50 per 1,000 miles delta

# Deal grade thresholds (% below market avg, after mileage adjustment)
GRADE_THRESHOLDS = [
    (20,  "🔥 Steal",       "20%+ below market — act fast"),
    (10,  "✅ Great Deal",   "10–20% below market"),
    (5,   "👍 Good Deal",    "5–10% below market"),
    (0,   "➡️  Fair Price",   "Within 5% of market"),
    (-10, "⚠️  Overpriced",   "5–10% above market"),
    (-99, "🚫 Way Overpriced","More than 10% above market"),
]


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class ScrapedListing:
    """Represents one listing pulled from CL or another scraping source."""
    asking_price: float
    year:         int
    make:         str
    model:        str
    mileage:      Optional[int]   = None
    trim:         Optional[str]   = None
    condition:    Optional[str]   = None   # "clean", "salvage", "rebuilt", etc.
    source_url:   Optional[str]   = None
    source_site:  Optional[str]   = None   # "craigslist", "facebook", etc.
    listing_id:   Optional[str]   = None
    region:       Optional[str]   = None   # "San Francisco Bay Area", "Medford, OR"
    zip_code:     Optional[str]   = None   # ZIP code for regional pricing


@dataclass
class DealResult:
    """Full output returned by DealScorer.score()"""
    # ── Identity ──
    year:          int
    make:          str
    model:         str
    trim:          Optional[str]
    condition:     Optional[str]

    # ── Prices ──
    asking_price:      float
    market_avg:        float
    market_min:        float
    market_max:        float
    market_median:     float
    adjusted_market:   float    # market_avg after mileage adjustment
    mileage:           Optional[int]
    market_avg_mileage:Optional[int]
    mileage_adjustment:float    # dollar amount added/subtracted

    # ── Score ──
    savings_vs_avg:    float    # asking - adjusted_market (negative = you save)
    pct_below_market:  float    # positive = good deal, negative = overpriced
    grade:             str      # e.g. "🔥 Steal"
    grade_description: str

    # ── Meta ──
    listings_count:    int      # how many listings the market avg is based on
    data_source:       str      # "cache" or "live_api"
    cache_age_hours:   Optional[float]
    source_url:        Optional[str]
    source_site:       Optional[str]
    scored_at:         str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        direction = "below" if self.savings_vs_avg < 0 else "above"
        savings   = abs(self.savings_vs_avg)
        return (
            f"{self.grade}\n"
            f"  {self.year} {self.make} {self.model} {self.trim or ''}\n"
            f"  Asking:  ${self.asking_price:,.0f}\n"
            f"  Market:  ${self.market_avg:,.0f} avg  "
            f"(${self.market_min:,.0f}–${self.market_max:,.0f})\n"
            f"  Adjusted market (mileage): ${self.adjusted_market:,.0f}\n"
            f"  You {'save' if self.savings_vs_avg < 0 else 'overpay'}: "
            f"${savings:,.0f} ({abs(self.pct_below_market):.1f}% {direction} market)\n"
            f"  {self.grade_description}\n"
            f"  Based on {self.listings_count:,} active listings  |  "
            f"Data: {self.data_source}"
        )


# ── Cache Manager ─────────────────────────────────────────────────────────────

class CacheManager:
    """Loads, reads, and updates the local JSON cache."""

    def __init__(self, path: Path = CACHE_FILE):
        self.path = path
        self._data: dict = {"metadata": {}, "vehicles": []}
        if path.exists():
            self._load()

    def _load(self):
        with open(self.path) as f:
            self._data = json.load(f)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def lookup(self, year: int, make: str, model: str, trim: Optional[str], region: Optional[str] = None) -> Optional[dict]:
        make_l  = make.lower()
        model_l = model.lower()
        trim_l  = trim.lower() if trim else None
        region_l = region.lower() if region else None

        candidates = [
            v for v in self._data.get("vehicles", [])
            if v.get("year") == year
            and v.get("make", "").lower()  == make_l
            and v.get("model", "").lower() == model_l
            and v.get("fetch_status") == "success"
        ]
        
        # Filter by region if specified
        if region_l:
            regional = [c for c in candidates if (c.get("region") or "").lower() == region_l]
            if regional:
                candidates = regional
            # If no regional data, fall back to national data (region=None in cache)
        
        if not candidates:
            return None

        if trim_l:
            exact = [c for c in candidates if (c.get("trim") or "").lower() == trim_l]
            match = exact[0] if exact else candidates[0]   # fall back to any trim
        else:
            match = candidates[0]

        fetched_at = self._data.get("metadata", {}).get("fetched_at")
        result = dict(match)
        result["_cache_age_hours"] = self._age_hours(fetched_at) if fetched_at else None
        return result

    def store(self, record: dict):
        """Upsert a freshly fetched vehicle record into the cache."""
        vehicles = self._data.setdefault("vehicles", [])
        # Remove any existing entry for this vehicle + region combination
        self._data["vehicles"] = [
            v for v in vehicles
            if not (
                v.get("year")  == record["year"]
                and v.get("make", "").lower()  == record["make"].lower()
                and v.get("model", "").lower() == record["model"].lower()
                and (v.get("trim") or "").lower() == (record.get("trim") or "").lower()
                and (v.get("region") or "").lower() == (record.get("region") or "").lower()
            )
        ]
        self._data["vehicles"].append(record)
        self._data.setdefault("metadata", {})["last_updated"] = (
            datetime.now(timezone.utc).isoformat()
        )
        self._save()
        region_label = f" [{record.get('region')}]" if record.get('region') else ""
        log.info(f"  Cache updated: {record['year']} {record['make']} {record['model']}{region_label}")

    @staticmethod
    def _age_hours(iso: str) -> float:
        dt = datetime.fromisoformat(iso)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


# ── Live API Fetcher ──────────────────────────────────────────────────────────

def fetch_live(year: int, make: str, model: str, trim: Optional[str], 
               zip_code: Optional[str] = None, radius: int = 100) -> Optional[dict]:
    """
    On cache miss: hit MarketCheck API directly.
    Result is stored back into the cache so future lookups are free.
    
    Args:
        zip_code: ZIP code for regional pricing (e.g., "94102" for SF)
        radius: Search radius in miles (default 100)
    """
    if not API_KEY:
        log.warning("No MARKETCHECK_API_KEY set — cannot do live lookup.")
        return None

    params = {
        "api_key":  API_KEY,
        "car_type": "used",
        "year":     year,
        "make":     make,
        "model":    model,
        "stats":    "price,miles",
        "rows":     0,
    }
    if trim:
        params["trim"] = trim
    if zip_code:
        params["zip"] = zip_code
        params["radius"] = radius

    label = f"{year} {make} {model} {trim or ''}".strip()
    region_label = f" (ZIP {zip_code}, {radius}mi)" if zip_code else " (national)"
    log.info(f"  Cache miss — live API call for: {label}{region_label}")

    try:
        resp = requests.get(f"{BASE_URL}/search/car/active", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        stats  = data.get("stats", {})
        price  = stats.get("price", {})
        miles  = stats.get("miles", {})
        count  = data.get("totalListings", data.get("num_found", 0))

        if not price or count == 0:
            log.warning(f"  No market data found for {label}{region_label}")
            return None

        record = {
            "year":           year,
            "make":           make,
            "model":          model,
            "trim":           trim,
            "zip_code":       zip_code,
            "radius":         radius if zip_code else None,
            "listings_count": count,
            "price_avg":      round(price.get("mean", 0)),
            "price_min":      round(price.get("min", 0)),
            "price_max":      round(price.get("max", 0)),
            "price_median":   round(price.get("median", 0)),
            "mileage_avg":    round(miles.get("mean", 0)),
            "fetch_status":   "success",
            "fetched_at":     datetime.now(timezone.utc).isoformat(),
        }
        return record

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        if code == 401:
            log.error("Invalid API key.")
        elif code == 429:
            log.warning("Rate limit hit on live call.")
        else:
            log.error(f"HTTP {code} on live call: {e}")
        return None
    except requests.exceptions.RequestException as e:
        log.error(f"Network error on live call: {e}")
        return None


# ── Scoring Logic ─────────────────────────────────────────────────────────────

def _grade(pct_below: float) -> tuple[str, str]:
    for threshold, grade, desc in GRADE_THRESHOLDS:
        if pct_below >= threshold:
            return grade, desc
    return GRADE_THRESHOLDS[-1][1], GRADE_THRESHOLDS[-1][2]


def _mileage_adjustment(listing_miles: Optional[int], market_avg_miles: Optional[int]) -> float:
    """
    Returns a dollar adjustment to apply to market_avg.
    Positive adjustment = car has fewer miles than avg = worth more = raise the bar.
    Negative adjustment = car has more miles than avg  = worth less = lower the bar.
    """
    if listing_miles is None or market_avg_miles is None:
        return 0.0
    delta_thousands = (market_avg_miles - listing_miles) / 1000
    return round(delta_thousands * MILEAGE_ADJUSTMENT_PER_1K, 2)


def _condition_note(condition: Optional[str]) -> str:
    if not condition:
        return ""
    c = condition.lower()
    if any(w in c for w in ["salvage", "rebuilt", "flood", "lemon"]):
        return f"⚠️  Condition flagged: '{condition}' — market value may not apply"
    return ""


# ── Main Scorer ───────────────────────────────────────────────────────────────

class DealScorer:
    """
    The main interface. Feed it a ScrapedListing, get back a DealResult.

    Usage:
        scorer  = DealScorer()
        listing = ScrapedListing(
            asking_price=18500,
            year=2021, make="Toyota", model="Camry",
            mileage=45000, trim="LE", condition="clean",
            source_url="https://craigslist.org/...",
            source_site="craigslist"
        )
        result = scorer.score(listing)
        print(result.summary())
    """

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.cache   = CacheManager(path=cache_path)
        self._scored = 0
        self._misses = 0

    def score(self, listing: ScrapedListing) -> Optional[DealResult]:
        """
        Score a single scraped listing. Returns None if no market data is found.
        Uses regional pricing if listing has region/zip_code set.
        """
        # 1. Cache lookup (fast path) - try regional first, fall back to national
        market = self.cache.lookup(
            listing.year, listing.make, listing.model, listing.trim, listing.region
        )
        data_source = "cache"

        # 2. Cache miss → live API call, then cache the result
        if market is None:
            self._misses += 1
            market = fetch_live(
                listing.year, listing.make, listing.model, listing.trim,
                listing.zip_code, radius=100
            )
            if market:
                # Add region to the record before caching
                if listing.region:
                    market["region"] = listing.region
                self.cache.store(market)
                data_source = "live_api"
            else:
                log.warning(
                    f"No market data for "
                    f"{listing.year} {listing.make} {listing.model} — skipping."
                )
                return None

        # 3. Mileage adjustment
        mil_adj      = _mileage_adjustment(listing.mileage, market.get("mileage_avg"))
        adj_market   = market["price_avg"] + mil_adj

        # 4. Score
        savings      = listing.asking_price - adj_market          # negative = good
        pct_below    = ((adj_market - listing.asking_price) / adj_market) * 100
        grade, desc  = _grade(pct_below)

        # 5. Condition warning (appended to grade description)
        cond_note    = _condition_note(listing.condition)
        if cond_note:
            desc = f"{desc}  |  {cond_note}"

        self._scored += 1

        return DealResult(
            year               = listing.year,
            make               = listing.make,
            model              = listing.model,
            trim               = listing.trim,
            condition          = listing.condition,
            asking_price       = listing.asking_price,
            market_avg         = market["price_avg"],
            market_min         = market["price_min"],
            market_max         = market["price_max"],
            market_median      = market["price_median"],
            adjusted_market    = round(adj_market, 2),
            mileage            = listing.mileage,
            market_avg_mileage = market.get("mileage_avg"),
            mileage_adjustment = mil_adj,
            savings_vs_avg     = round(savings, 2),
            pct_below_market   = round(pct_below, 1),
            grade              = grade,
            grade_description  = desc,
            listings_count     = market.get("listings_count", 0),
            data_source        = data_source,
            cache_age_hours    = market.get("_cache_age_hours"),
            source_url         = listing.source_url,
            source_site        = listing.source_site,
            scored_at          = datetime.now(timezone.utc).isoformat(),
        )

    def score_batch(self, listings: list[ScrapedListing],
                    delay: float = 0.3) -> list[DealResult]:
        """
        Score a list of scraped listings. Adds a small delay between live
        API calls to stay within rate limits.
        """
        results = []
        for i, listing in enumerate(listings):
            result = self.score(listing)
            if result:
                results.append(result)
            # Only delay if this listing triggered a live call
            if self._misses > 0 and i < len(listings) - 1:
                time.sleep(delay)

        log.info(
            f"Batch complete: {len(results)}/{len(listings)} scored  |  "
            f"{self._misses} live API calls made"
        )
        return results

    def stats(self) -> dict:
        return {"scored": self._scored, "live_api_calls": self._misses}
