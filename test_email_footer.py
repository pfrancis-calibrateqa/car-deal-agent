#!/usr/bin/env python3
"""
Test script to verify email footer with different scenarios.
"""

import sys
sys.path.insert(0, 'src')

from search_agent import build_email_html, ErrorHandler
from datetime import datetime, timedelta

print("Testing email footer scenarios...\n")

# Test 1: Email with listings (normal case)
print("1. Testing footer with listings...")
test_results_with_listings = {
    "San Francisco Bay Area": [
        {
            "title": "2020 Honda CR-V",
            "url": "https://test.com/1",
            "price": 23000,
            "mileage": 45000,
            "color": "Blue",
            "source": "Craigslist",
            "region": "San Francisco Bay Area",
            "score": 0.65,
            "deal_grade": "✅ Great Deal",
            "deal_pct": 15.0,
            "deal_vs_avg": -3000,
            "market_avg": 26000,
            "posted": "2026-03-05",
            "year": 2020,
            "make": "Honda",
            "model": "CR-V"
        }
    ]
}

error_handler = ErrorHandler()
html = build_email_html(test_results_with_listings, error_handler)

# Check footer contains expected elements
assert "Last successful run:" in html or "First run" in html
assert "Script version:" in html
assert "Generated:" in html
print("✓ Footer displays correctly with listings\n")

# Test 2: Email with no listings
print("2. Testing footer with no listings...")
test_results_no_listings = {
    "San Francisco Bay Area": [],
    "Medford, OR": []
}

html_no_listings = build_email_html(test_results_no_listings, error_handler)

# Check troubleshooting section appears
assert "No New Listings Found" in html_no_listings
assert "This could mean:" in html_no_listings
assert "What you can do:" in html_no_listings
assert "Check back tomorrow" in html_no_listings
print("✓ Troubleshooting section appears when no listings\n")

# Test 3: Email with errors
print("3. Testing footer with errors...")
error_handler_with_errors = ErrorHandler()
try:
    raise ConnectionError("Network timeout")
except Exception as e:
    error_handler_with_errors.record_error("Craigslist", e)

html_with_errors = build_email_html(test_results_with_listings, error_handler_with_errors)

# Check error section appears
assert "SCRAPING ISSUES" in html_with_errors
assert "Craigslist" in html_with_errors
assert "ConnectionError" in html_with_errors
print("✓ Error section appears in email\n")

# Test 4: Email with last successful run timestamp
print("4. Testing footer with last successful run...")
error_handler_with_last_run = ErrorHandler()
error_handler_with_last_run.last_successful_run = datetime.now() - timedelta(days=1)

html_with_last_run = build_email_html(test_results_with_listings, error_handler_with_last_run)

# Check last run timestamp appears
assert "Last successful run:" in html_with_last_run
print("✓ Last successful run timestamp displays\n")

# Write test outputs
with open("test_footer_with_listings.html", "w") as f:
    f.write(html)
print("✓ Generated: test_footer_with_listings.html")

with open("test_footer_no_listings.html", "w") as f:
    f.write(html_no_listings)
print("✓ Generated: test_footer_no_listings.html")

with open("test_footer_with_errors.html", "w") as f:
    f.write(html_with_errors)
print("✓ Generated: test_footer_with_errors.html")

print("\n✅ All footer tests passed!")
print("   Open the generated HTML files to visually verify the footer display.")
