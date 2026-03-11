#!/usr/bin/env python3
"""
Test weighted trim average calculation
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from deal_scorer import DealScorer, ScrapedListing

def test_trim_average():
    """Test that unknown trims get weighted average from all trim-specific data."""
    
    scorer = DealScorer()
    
    print("\n" + "="*80)
    print("Testing Weighted Trim Average Calculation")
    print("="*80)
    
    print("\nCache data for 2021 Mazda CX-5 in Medford, OR:")
    print("  Touring:       $28,026 (1 listing)")
    print("  Grand Touring: $23,068 (1 listing)")
    print("  Generic:       $25,547 (2 listings)")
    print("\nExpected weighted average from trim-specific data:")
    print("  (28026 * 1 + 23068 * 1) / 2 = $25,547")
    
    # Test with unknown trim "EX" (should use weighted average)
    listing = ScrapedListing(
        asking_price=20000,
        year=2021,
        make="Mazda",
        model="CX-5",
        mileage=40000,
        trim="EX",  # Unknown trim
        region="Medford, OR",
        zip_code="97501"
    )
    
    result = scorer.score(listing)
    
    if result:
        print(f"\n{'='*80}")
        print(f"Listing with unknown trim 'EX':")
        print(f"  Market Median: ${result.market_median:,}")
        print(f"  Market Avg:    ${result.market_avg:,}")
        print(f"  Listings:      {result.listings_count}")
        print(f"  Data source:   {result.data_source}")
    
    # Test with no trim (should also use weighted average)
    listing2 = ScrapedListing(
        asking_price=20000,
        year=2021,
        make="Mazda",
        model="CX-5",
        mileage=40000,
        trim=None,  # No trim
        region="Medford, OR",
        zip_code="97501"
    )
    
    result2 = scorer.score(listing2)
    
    if result2:
        print(f"\n{'='*80}")
        print(f"Listing with no trim:")
        print(f"  Market Median: ${result2.market_median:,}")
        print(f"  Market Avg:    ${result2.market_avg:,}")
        print(f"  Listings:      {result2.listings_count}")
        print(f"  Data source:   {result2.data_source}")
    
    # Test with known trim (should use exact match)
    listing3 = ScrapedListing(
        asking_price=20000,
        year=2021,
        make="Mazda",
        model="CX-5",
        mileage=40000,
        trim="Touring",  # Known trim
        region="Medford, OR",
        zip_code="97501"
    )
    
    result3 = scorer.score(listing3)
    
    if result3:
        print(f"\n{'='*80}")
        print(f"Listing with known trim 'Touring':")
        print(f"  Market Median: ${result3.market_median:,}")
        print(f"  Market Avg:    ${result3.market_avg:,}")
        print(f"  Listings:      {result3.listings_count}")
        print(f"  Data source:   {result3.data_source}")
    
    print("\n" + "="*80)
    print("Test complete!")
    print("="*80)


if __name__ == "__main__":
    test_trim_average()
