#!/usr/bin/env python3
"""
Test to preview the "How We Rate Deals" section in the email (desktop and mobile)
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from search_agent import build_email_html, ErrorHandler


def test_how_we_rate_section():
    """Generate a test email to preview the 'How We Rate Deals' section."""
    
    print("\n" + "="*60)
    print("Generating Test Email with 'How We Rate Deals' Section")
    print("="*60 + "\n")
    
    # Create mock results with one listing
    mock_listing = {
        "title": "2020 Honda CR-V EX",
        "year": 2020,
        "make": "Honda",
        "model": "CR-V",
        "trim": "EX",
        "price": 23000,
        "mileage": 50000,
        "color": "Silver",
        "url": "https://example.com/listing",
        "source": "Craigslist",
        "region": "San Francisco Bay Area",
        "posted": "2026-03-05",
        "score": 0.75,
        "deal_grade": "✅ Great Deal",
        "deal_pct": 12.5,
        "deal_vs_avg": -3200,
        "market_avg": 26200,
        "deal_data_src": "cache"
    }
    
    results_by_region = {
        "San Francisco Bay Area": [mock_listing]
    }
    
    # Create error handler
    error_handler = ErrorHandler()
    
    # Build email HTML
    html = build_email_html(results_by_region, error_handler)
    
    # Write to file
    output_file = Path("email_how_we_rate_preview.html")
    with open(output_file, "w") as f:
        f.write(html)
    
    print(f"✅ Test email generated: {output_file}")
    print()
    print("Preview the email by opening the file in your browser:")
    print(f"  open {output_file}")
    print()
    print("What to check:")
    print()
    print("DESKTOP VIEW (default):")
    print("  1. 'How We Rate Deals' section appears below the header")
    print("  2. Info icon (ℹ) is visible")
    print("  3. Section is collapsed by default")
    print("  4. Click to expand shows full explanation")
    print("  5. Total market listings count is displayed")
    print("  6. Regional coverage is shown")
    print()
    print("MOBILE VIEW (resize browser to <600px width):")
    print("  1. Desktop table disappears")
    print("  2. Mobile cards appear")
    print("  3. 'How We Rate Deals' section appears at top of mobile view")
    print("  4. Tap to expand works on mobile")
    print("  5. Text is readable without zooming")
    print("  6. All bullet points display correctly")
    print()
    print("="*60 + "\n")


if __name__ == "__main__":
    test_how_we_rate_section()
