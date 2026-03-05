#!/usr/bin/env python3
"""
Test script to verify deal scoring integration works end-to-end
"""
import sys
sys.path.insert(0, 'src')

from deal_scorer import DealScorer, ScrapedListing
from dotenv import load_dotenv
import os

load_dotenv()

print("=" * 60)
print("Testing Deal Scoring Integration")
print("=" * 60)

# Check environment
print(f"\n1. Environment Check:")
print(f"   API Key: {os.getenv('MARKETCHECK_API_KEY')[:10]}..." if os.getenv('MARKETCHECK_API_KEY') else "   API Key: NOT SET")
print(f"   Secret: {os.getenv('MARKETCHECK_SECRET')[:10]}..." if os.getenv('MARKETCHECK_SECRET') else "   Secret: NOT SET")

# Create scorer
print(f"\n2. Creating DealScorer...")
scorer = DealScorer()
print(f"   ✓ DealScorer created successfully")

# Test with a few sample listings
test_cases = [
    {
        "name": "2013 Honda CR-V - Good Deal",
        "listing": ScrapedListing(
            asking_price=10000,
            year=2013,
            make="Honda",
            model="CR-V",
            mileage=120000,
            trim=None,
            condition=None,
            source_url="https://test.com/1",
            source_site="craigslist"
        )
    },
    {
        "name": "2020 Honda CR-V - Fair Price",
        "listing": ScrapedListing(
            asking_price=23000,
            year=2020,
            make="Honda",
            model="CR-V",
            mileage=65000,
            trim=None,
            condition=None,
            source_url="https://test.com/2",
            source_site="craigslist"
        )
    },
    {
        "name": "2023 Mazda CX-5 - Overpriced",
        "listing": ScrapedListing(
            asking_price=28000,
            year=2023,
            make="Mazda",
            model="CX-5",
            mileage=30000,
            trim=None,
            condition=None,
            source_url="https://test.com/3",
            source_site="autotrader"
        )
    }
]

print(f"\n3. Testing {len(test_cases)} sample listings:")
print("-" * 60)

for i, test in enumerate(test_cases, 1):
    print(f"\n   Test {i}: {test['name']}")
    result = scorer.score(test['listing'])
    
    if result:
        print(f"   ✓ Grade: {result.grade}")
        print(f"   ✓ % vs Market: {result.pct_below_market:.1f}%")
        print(f"   ✓ Savings: ${result.savings_vs_avg:,.0f}")
        print(f"   ✓ Market Avg: ${result.market_avg:,.0f}")
        print(f"   ✓ Data Source: {result.data_source}")
    else:
        print(f"   ✗ No result returned (no market data found)")

# Show stats
print(f"\n4. Scorer Statistics:")
stats = scorer.stats()
print(f"   Listings scored: {stats['scored']}")
print(f"   Live API calls: {stats['live_api_calls']}")
print(f"   Cache hits: {stats['scored'] - stats['live_api_calls']}")

print("\n" + "=" * 60)
print("Integration test complete!")
print("=" * 60)
