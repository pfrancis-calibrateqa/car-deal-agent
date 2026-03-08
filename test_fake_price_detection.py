#!/usr/bin/env python3
"""
Test fake price detection and extraction logic
"""
import sys
sys.path.insert(0, 'src')

# Import the functions
from search_agent import is_suspicious_price, extract_real_price_from_text

print("=" * 60)
print("FAKE PRICE DETECTION TESTS")
print("=" * 60)

# Test 1: Suspicious price detection
print("\n1. Testing suspicious price detection:")
print("-" * 60)

test_prices = [
    (1, True, "Classic fake price"),
    (10, True, "Another common fake"),
    (100, True, "Placeholder price"),
    (123, True, "Sequential fake"),
    (500, True, "Down payment amount"),
    (1000, True, "Round placeholder"),
    (1234, True, "Sequential fake"),
    (1999, True, "Just under $2000 threshold"),
    (2000, False, "At threshold - legitimate"),
    (5000, False, "Legitimate low price"),
    (15000, False, "Normal price"),
    (25000, False, "Normal price"),
]

for price, expected, description in test_prices:
    result = is_suspicious_price(price)
    status = "✅" if result == expected else "❌"
    print(f"{status} ${price:,} -> {result} ({description})")

# Test 2: Real price extraction
print("\n2. Testing real price extraction from text:")
print("-" * 60)

test_cases = [
    (
        "Great car! Asking $15,000 OBO. Clean title, runs perfect.",
        2020,
        15000,
        "Standard asking price format"
    ),
    (
        "Price: $22,500 firm. No trades. Serious buyers only.",
        2021,
        22500,
        "Price with 'firm' keyword"
    ),
    (
        "Selling for 18500. Has 50k miles. Call for details.",
        2019,
        18500,
        "Plain number format"
    ),
    (
        "Down payment $2000, asking $16,000 total. Great deal!",
        2018,
        16000,
        "Multiple prices (should pick highest)"
    ),
    (
        "Monthly payment $350. Asking price $19,995 OBO.",
        2020,
        19995,
        "Monthly payment vs asking price"
    ),
    (
        "Call for price. Must see to appreciate.",
        2019,
        None,
        "No price in description"
    ),
    (
        "Asking 25k OBO. Clean title, well maintained.",
        2022,
        25000,
        "Price with 'k' suffix (should be handled by pattern)"
    ),
    (
        "$1 (real price $17,500) - serious inquiries only",
        2020,
        17500,
        "Explicit fake price with real price"
    ),
]

for text, year, expected, description in test_cases:
    result = extract_real_price_from_text(text, year)
    status = "✅" if result == expected else "❌"
    result_str = f"${result:,}" if result else "None"
    expected_str = f"${expected:,}" if expected else "None"
    print(f"{status} {description}")
    print(f"   Text: {text[:60]}...")
    print(f"   Expected: {expected_str}, Got: {result_str}")
    print()

# Test 3: Integration test
print("\n3. Integration test: Full workflow")
print("-" * 60)

mock_listings = [
    {
        "title": "2020 Honda CR-V - Great Condition",
        "price": 1,  # Fake price
        "year": 2020,
        "description": "Asking $18,500 OBO. Clean title, 45k miles."
    },
    {
        "title": "2019 Mazda CX-5 Touring",
        "price": 100,  # Fake price
        "year": 2019,
        "description": "Price: $16,900 firm. No trades."
    },
    {
        "title": "2021 Honda CR-V EX",
        "price": 1234,  # Fake price
        "year": 2021,
        "description": "Call for details. Must see!"  # No real price
    },
    {
        "title": "2022 Mazda CX-5 Carbon",
        "price": 25000,  # Real price
        "year": 2022,
        "description": "Excellent condition, low miles."
    },
]

for listing in mock_listings:
    print(f"\nListing: {listing['title']}")
    print(f"  Initial price: ${listing['price']:,}")
    
    if is_suspicious_price(listing['price']):
        print(f"  ⚠️  Suspicious price detected!")
        real_price = extract_real_price_from_text(listing['description'], listing['year'])
        
        if real_price:
            print(f"  ✅ Found real price: ${real_price:,}")
            listing['price'] = real_price
        else:
            print(f"  ❌ Could not find real price - would filter out")
    else:
        print(f"  ✅ Price looks legitimate")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
