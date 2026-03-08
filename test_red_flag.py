#!/usr/bin/env python3
"""Test the red flag feature for suspiciously low prices (≥45% below market)"""
import sys
sys.path.insert(0, 'src')

from deal_scorer import DealScorer

# Read and execute the search_agent.py file directly
with open('src/search_agent.py', 'r') as f:
    code = f.read()

# Replace the main execution block to prevent it from running
code = code.replace('if __name__ == "__main__":', 'if False:')

# Execute in current namespace
exec(code)

# Create scorer
scorer = DealScorer()

# Create mock listings with different deal percentages
# Including one with ≥45% below market to trigger red flag
mock_listings = [
    {
        'source': 'Craigslist',
        'title': '2020 Honda CR-V EX - Normal Good Deal',
        'price': 20000,
        'mileage': 50000,
        'year': 2020,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://sfbay.craigslist.org/test1',
        'color': 'Silver',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.72
    },
    {
        'source': 'Craigslist',
        'title': '2019 Honda CR-V Touring - SUSPICIOUSLY LOW PRICE',
        'price': 11000,  # Way too low for a 2019 Touring - should trigger red flag
        'mileage': 60000,
        'year': 2019,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://sfbay.craigslist.org/test2',
        'color': 'Blue',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.85
    },
    {
        'source': 'Craigslist',
        'title': '2021 Mazda CX-5 Signature - EXTREME DEAL',
        'price': 14000,  # Extremely low for a 2021 Signature trim
        'mileage': 40000,
        'year': 2021,
        'make': 'Mazda',
        'model': 'CX-5',
        'url': 'https://sfbay.craigslist.org/test3',
        'color': 'Red',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.88
    },
]

print("Testing red flag feature for suspiciously low prices...")
print("="*70)

for listing in mock_listings:
    listing = apply_deal_score(listing, scorer)
    deal_pct = listing.get('deal_pct', 0)
    deal_grade = listing.get('deal_grade', 'No data')
    
    print(f"\n{listing['title']}")
    print(f"  Price: ${listing['price']:,}")
    print(f"  Deal Grade: {deal_grade}")
    print(f"  % Below Market: {deal_pct:.1f}%")
    
    if deal_pct >= 45:
        print(f"  🚩 RED FLAG: This deal is TOO GOOD TO BE TRUE (≥45% below market)")
        print(f"     User should verify carefully - may be salvage, scam, or data error")
    else:
        print(f"  ✅ Normal deal range (no red flag)")

# Generate email to verify red flag appears in HTML
print("\n" + "="*70)
print("Generating email HTML to verify red flag display...")
print("="*70)

results = {
    'San Francisco Bay Area': mock_listings,
}

html = build_email_html(results)

# Check if red flag emoji is in the HTML
if '🚩' in html:
    print("\n✅ SUCCESS: Red flag emoji (🚩) found in email HTML")
    print("   The red flag will appear next to the deal grade for suspicious deals")
else:
    print("\n❌ FAILURE: Red flag emoji NOT found in email HTML")
    print("   Check if any listings have deal_pct >= 45%")

# Save to file
output_file = 'email_red_flag_test.html'
with open(output_file, 'w') as f:
    f.write(html)

print(f"\n📧 Email preview saved to: {output_file}")
print(f"   Open this file in your browser to see the red flag in action")

# Count red flags in HTML
red_flag_count = html.count('🚩')
print(f"\n🚩 Red flags in email: {red_flag_count}")
