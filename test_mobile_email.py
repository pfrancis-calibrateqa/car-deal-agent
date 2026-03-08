#!/usr/bin/env python3
"""
Test script to generate a mobile-responsive email preview.
"""

import sys
sys.path.insert(0, 'src')

from search_agent import build_email_html

# Sample test data
test_results = {
    "San Francisco Bay Area": [
        {
            "title": "2013 Honda CR-V EXL AWD - Great Deal",
            "url": "https://sfbay.craigslist.org/test1",
            "price": 10000,
            "mileage": 120000,
            "color": "Silver",
            "source": "Craigslist",
            "region": "San Francisco Bay Area",
            "score": 0.72,
            "deal_grade": "✅ Great Deal",
            "deal_pct": 18.4,
            "deal_vs_avg": -2258,
            "market_avg": 12258,
            "posted": "2026-03-05",
            "year": 2013,
            "make": "Honda",
            "model": "CR-V",
            "trim": "EXL"
        },
        {
            "title": "2020 Honda CR-V Touring AWD",
            "url": "https://sfbay.craigslist.org/test2",
            "price": 23000,
            "mileage": 45000,
            "color": "Blue",
            "source": "Craigslist",
            "region": "San Francisco Bay Area",
            "score": 0.65,
            "deal_grade": "➡️  Fair Price",
            "deal_pct": 4.8,
            "deal_vs_avg": -1160,
            "market_avg": 24160,
            "posted": "2026-03-05",
            "year": 2020,
            "make": "Honda",
            "model": "CR-V",
            "trim": "Touring"
        },
        {
            "title": "2023 Mazda CX-5 Carbon Edition",
            "url": "https://sfbay.craigslist.org/test3",
            "price": 27000,
            "mileage": 21000,
            "color": "Black",
            "source": "Craigslist",
            "region": "San Francisco Bay Area",
            "score": 0.68,
            "deal_grade": "⚠️  Overpriced",
            "deal_pct": -5.7,
            "deal_vs_avg": 1461,
            "market_avg": 25539,
            "posted": "2026-03-05",
            "year": 2023,
            "make": "Mazda",
            "model": "CX-5",
            "trim": "Carbon"
        },
        {
            "title": "2022 Honda CR-V EX AWD Hybrid",
            "url": "https://stockton.craigslist.org/test4",
            "price": 21900,
            "mileage": 52000,
            "color": "White",
            "source": "Craigslist",
            "region": "San Francisco Bay Area",
            "score": 0.56,
            "deal_grade": "✅ Great Deal",
            "deal_pct": 17.4,
            "deal_vs_avg": -4617,
            "market_avg": 26517,
            "posted": "2026-03-05",
            "year": 2022,
            "make": "Honda",
            "model": "CR-V",
            "trim": "EX"
        }
    ],
    "Medford, OR": []
}

# Generate HTML
html = build_email_html(test_results)

# Write to file
with open("email_mobile_preview.html", "w") as f:
    f.write(html)

print("✓ Mobile email preview generated: email_mobile_preview.html")
print("  Open this file in a browser and resize to <600px width to see mobile layout")
