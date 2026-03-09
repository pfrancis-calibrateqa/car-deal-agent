#!/usr/bin/env python3
"""
Analyze cache coverage to find missing market data
"""

import json
from pathlib import Path

# Load config
config_path = Path("config/search_criteria.json")
with open(config_path) as f:
    config = json.load(f)

# Load cache
cache_path = Path("src/car_values_cache.json")
with open(cache_path) as f:
    cache = json.load(f)

# Common trims
COMMON_TRIMS = {
    "Honda CR-V": ["LX", "EX", "EX-L", "Touring", "Sport"],
    "Mazda CX-5": ["Sport", "Touring", "Grand Touring", "Carbon", "Signature"],
}

print("\n" + "="*80)
print("CACHE COVERAGE ANALYSIS")
print("="*80 + "\n")

# Build expected vehicles list
expected = []
for search in config["searches"]:
    make = search["make"]
    model = search["model"]
    years = search["years"]
    model_key = f"{make} {model}"
    trims = COMMON_TRIMS.get(model_key, [])
    
    for region in config["regions"]:
        region_name = region["name"]
        for year in years:
            # Generic (no trim)
            expected.append({
                "year": year,
                "make": make,
                "model": model,
                "trim": None,
                "region": region_name
            })
            # Each trim
            for trim in trims:
                expected.append({
                    "year": year,
                    "make": make,
                    "model": model,
                    "trim": trim,
                    "region": region_name
                })

print(f"Expected vehicles in cache: {len(expected)}")
print(f"Vehicles in cache: {len(cache['vehicles'])}")
print()

# Check what's in cache
cache_vehicles = cache["vehicles"]
found = 0
missing = []
no_data = []

for exp in expected:
    # Find matching vehicle in cache
    match = None
    for cv in cache_vehicles:
        if (cv.get("year") == exp["year"] and
            cv.get("make") == exp["make"] and
            cv.get("model") == exp["model"] and
            cv.get("trim") == exp["trim"] and
            cv.get("region") == exp["region"]):
            match = cv
            break
    
    if match is None:
        missing.append(exp)
    elif match.get("fetch_status") == "no_data":
        no_data.append(exp)
    else:
        found += 1

print(f"✅ Found with data: {found}")
print(f"⚠️  Found but no market data: {len(no_data)}")
print(f"❌ Missing from cache: {len(missing)}")
print()

if no_data:
    print("="*80)
    print("VEHICLES WITH NO MARKET DATA (fetch_status='no_data')")
    print("="*80)
    for v in no_data[:20]:  # Show first 20
        trim_str = f" {v['trim']}" if v['trim'] else " (all trims)"
        print(f"  {v['year']} {v['make']} {v['model']}{trim_str} [{v['region']}]")
    if len(no_data) > 20:
        print(f"  ... and {len(no_data) - 20} more")
    print()

if missing:
    print("="*80)
    print("VEHICLES MISSING FROM CACHE")
    print("="*80)
    for v in missing[:20]:  # Show first 20
        trim_str = f" {v['trim']}" if v['trim'] else " (all trims)"
        print(f"  {v['year']} {v['make']} {v['model']}{trim_str} [{v['region']}]")
    if len(missing) > 20:
        print(f"  ... and {len(missing) - 20} more")
    print()

# Check if cache has regional data
has_regional = any(v.get("region") for v in cache_vehicles)
print("="*80)
print(f"Cache has regional data: {'✅ YES' if has_regional else '❌ NO'}")
print("="*80)

if not has_regional:
    print()
    print("⚠️  WARNING: Cache does not have regional pricing!")
    print("   The cache needs to be refreshed to include regional data.")
    print("   Run: python src/fetch_car_values.py")
    print()

print()
