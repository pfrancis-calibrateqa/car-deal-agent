"""
used_car_values/car_value_lookup.py
=====================================
Application-facing module. Reads the local car_values_cache.json file and
provides a simple lookup interface. Your app imports this — it never touches
the API directly. The cache is refreshed separately by fetch_car_values.py.

Usage example:
    from car_value_lookup import CarValueLookup

    lookup = CarValueLookup()
    result = lookup.get("Toyota", "Camry", 2021, trim="LE")
    print(result)
    # {
    #   "year": 2021, "make": "Toyota", "model": "Camry", "trim": "LE",
    #   "price_avg": 24500, "price_min": 19900, "price_max": 31000,
    #   "price_median": 24100, "mileage_avg": 28400,
    #   "listings_count": 312, "cache_age_hours": 4.2
    # }
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "car_values_cache.json"
STALE_AFTER_HOURS = 48   # warn if cache is older than this


class CarValueLookup:
    """
    Reads the local car values cache and provides fuzzy lookup by
    year / make / model / trim. Thread-safe for read operations.
    """

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.cache_path = cache_path
        self._cache = None
        self._load()

    def _load(self):
        """Load (or reload) the cache from disk."""
        if not self.cache_path.exists():
            raise FileNotFoundError(
                f"Cache file not found: {self.cache_path}\n"
                "Run fetch_car_values.py first to populate it."
            )
        with open(self.cache_path) as f:
            self._cache = json.load(f)

        fetched_at = self._cache["metadata"].get("fetched_at")
        if fetched_at:
            age_hours = self._cache_age_hours(fetched_at)
            if age_hours > STALE_AFTER_HOURS:
                log.warning(
                    f"Car value cache is {age_hours:.1f} hours old. "
                    f"Consider re-running fetch_car_values.py."
                )

    @staticmethod
    def _cache_age_hours(fetched_at_iso: str) -> float:
        fetched = datetime.fromisoformat(fetched_at_iso)
        now = datetime.now(timezone.utc)
        return (now - fetched).total_seconds() / 3600

    def get(
        self,
        make: str,
        model: str,
        year: int,
        trim: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Look up a vehicle's cached market value.

        Matching is case-insensitive. If a trim is provided, it tries an exact
        match first, then falls back to any trim for that year/make/model.

        Returns a dict with pricing data, or None if not found.
        """
        make_l  = make.lower()
        model_l = model.lower()
        trim_l  = trim.lower() if trim else None

        vehicles = self._cache.get("vehicles", [])
        candidates = [
            v for v in vehicles
            if v.get("make", "").lower()  == make_l
            and v.get("model", "").lower() == model_l
            and v.get("year")              == year
            and v.get("fetch_status")      == "success"
        ]

        if not candidates:
            return None

        # Prefer exact trim match if requested
        if trim_l:
            exact = [c for c in candidates if (c.get("trim") or "").lower() == trim_l]
            match = exact[0] if exact else candidates[0]
        else:
            match = candidates[0]

        # Enrich response with cache freshness info
        fetched_at = self._cache["metadata"].get("fetched_at")
        result = dict(match)
        result["cache_age_hours"] = round(self._cache_age_hours(fetched_at), 1) if fetched_at else None
        result["data_source"] = self._cache["metadata"].get("source")
        return result

    def all_vehicles(self) -> list[dict]:
        """Return all successfully fetched vehicles in the cache."""
        return [
            v for v in self._cache.get("vehicles", [])
            if v.get("fetch_status") == "success"
        ]

    def cache_info(self) -> dict:
        """Return metadata about the cache."""
        meta = self._cache.get("metadata", {})
        fetched_at = meta.get("fetched_at")
        return {
            "fetched_at":          fetched_at,
            "cache_age_hours":     round(self._cache_age_hours(fetched_at), 1) if fetched_at else None,
            "vehicles_with_data":  meta.get("vehicles_with_data"),
            "source":              meta.get("source"),
        }


# ── Example usage (run this file directly to test) ───────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    lookup = CarValueLookup()

    print("\n── Cache Info ──────────────────────────────────────")
    info = lookup.cache_info()
    for k, v in info.items():
        print(f"  {k}: {v}")

    print("\n── Sample Lookups ──────────────────────────────────")
    test_vehicles = [
        ("Toyota",  "Camry",    2021, "LE"),
        ("Honda",   "Civic",    2022, "EX"),
        ("Ford",    "F-150",    2020, "XLT"),
        ("Tesla",   "Model 3",  2021, None),
        ("Mazda",   "CX-5",     2020, None),   # not in cache — tests None return
    ]

    for make, model, year, trim in test_vehicles:
        result = lookup.get(make, model, year, trim)
        label = f"{year} {make} {model} {trim or '(any trim)'}".strip()
        if result:
            print(
                f"  {label}: "
                f"avg=${result['price_avg']:,}  "
                f"({result['price_min']:,}–{result['price_max']:,})  "
                f"{result['mileage_avg']:,} avg miles  "
                f"[{result['listings_count']} listings]"
            )
        else:
            print(f"  {label}: ── not found in cache")
