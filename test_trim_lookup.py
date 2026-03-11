#!/usr/bin/env python3
"""
Test trim-specific market data lookup
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from deal_scorer import DealScorer, ScrapedListing

def test_trim_lookup():
    """Test that different trims get different market prices."""
    
    scorer = DealScorer()
    
    print("\n" + "="*80)
    print("Testing Trim-Specific Market Data Lookup")
    print("="*80)
    
    # Test 2019 Mazda CX-5 with different trims in SF Bay Area
    test_cases = [
        ("Sport", "Should get Sport-specific price (~$16,310)"),
        ("Touring", "Should get Touring-specific price (~$18,998)"),
        ("Grand Touring", "Should get Grand Touring-specific price (~$19,497)"),
        ("Signature", "Should get Signature-specific price (~$21,998)"),
        ("Carbon", "No data - should fall back to generic (~$19,744)"),
    ]
    
    for trim, expected in test_cases:
        listing = ScrapedListing(
            asking_price=20000,
            year=2019,
            make="Mazda",
            model="CX-5",
            mileage=50000,
            trim=trim,
            region="San Francisco Bay Area",
            zip_code="94102"
        )
        
        result = scorer.score(listing)
        
        if result:
            print(f"\n{trim:15} → Market Median: ${result.market_median:,}  |  Market Avg: ${result.market_avg:,}")
            print(f"                Expected: {expected}")
        else:
            print(f"\n{trim:15} → NO DATA FOUND")
    
    print("\n" + "="*80)
    print("Test complete!")
    print("="*80)


if __name__ == "__main__":
    test_trim_lookup()
