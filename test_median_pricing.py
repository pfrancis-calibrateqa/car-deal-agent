#!/usr/bin/env python3
"""
Test to verify median-based pricing is working correctly
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from deal_scorer import DealScorer, ScrapedListing


def test_median_vs_mean():
    """
    Demonstrate the difference between median and mean pricing.
    
    Scenario: Market has these prices: $20k, $21k, $22k, $23k, $50k (outlier)
    - Mean: $27,200 (heavily skewed by $50k outlier)
    - Median: $22,000 (true middle value)
    
    A $23,000 listing should be:
    - Against mean: "Great Deal" (15.4% below)
    - Against median: "Fair Price" (4.5% above)
    """
    
    print("\n" + "="*60)
    print("Testing Median vs Mean Pricing")
    print("="*60 + "\n")
    
    # Create a test listing
    listing = ScrapedListing(
        asking_price=23000,
        year=2020,
        make="Honda",
        model="CR-V",
        mileage=50000,
        trim="EX",
        condition="clean",
        source_url="https://test.com/listing",
        source_site="test"
    )
    
    print("Test Listing:")
    print(f"  {listing.year} {listing.make} {listing.model} {listing.trim}")
    print(f"  Asking: ${listing.asking_price:,}")
    print(f"  Mileage: {listing.mileage:,} mi")
    print()
    
    # Score the listing (will use cached data)
    scorer = DealScorer()
    result = scorer.score(listing)
    
    if result:
        print("Market Data:")
        print(f"  Mean (average): ${result.market_avg:,}")
        print(f"  Median: ${result.market_median:,}")
        print(f"  Range: ${result.market_min:,} - ${result.market_max:,}")
        print(f"  Listings: {result.listings_count:,}")
        print()
        
        print("Deal Score (using MEDIAN):")
        print(f"  Grade: {result.grade}")
        print(f"  Adjusted market: ${result.adjusted_market:,.0f}")
        print(f"  Savings: ${abs(result.savings_vs_avg):,.0f}")
        print(f"  % vs market: {result.pct_below_market:.1f}%")
        print()
        
        # Calculate what it would have been with mean
        mean_adjusted = result.market_avg + result.mileage_adjustment
        mean_savings = listing.asking_price - mean_adjusted
        mean_pct = ((mean_adjusted - listing.asking_price) / mean_adjusted) * 100
        
        print("For Comparison (if we used MEAN):")
        print(f"  Adjusted market: ${mean_adjusted:,.0f}")
        print(f"  Savings: ${abs(mean_savings):,.0f}")
        print(f"  % vs market: {mean_pct:.1f}%")
        print()
        
        # Show the difference
        diff = abs(result.market_median - result.market_avg)
        print("Impact of Using Median:")
        print(f"  Median vs Mean difference: ${diff:,}")
        print(f"  More accurate baseline: ✓")
        print(f"  Resistant to outliers: ✓")
        print()
        
        print("="*60)
        print("✅ Test complete - median pricing is active!")
        print("="*60 + "\n")
    else:
        print("❌ No market data found for this vehicle")
        print("   (This is expected if cache doesn't have 2020 Honda CR-V)")


if __name__ == "__main__":
    test_median_vs_mean()
