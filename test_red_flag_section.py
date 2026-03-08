#!/usr/bin/env python3
"""Test the red flag section in email layout"""
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

# Create mock listings with mix of normal and red-flagged deals
mock_listings = [
    # Normal good deals
    {
        'source': 'Craigslist',
        'title': '2020 Honda CR-V EX AWD - Clean Title',
        'price': 20000,
        'mileage': 50000,
        'year': 2020,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://sfbay.craigslist.org/normal1',
        'color': 'Silver',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.72
    },
    {
        'source': 'AutoTrader',
        'title': '2021 Mazda CX-5 Touring AWD',
        'price': 24000,
        'mileage': 35000,
        'year': 2021,
        'make': 'Mazda',
        'model': 'CX-5',
        'url': 'https://autotrader.com/normal2',
        'color': 'Blue',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.75
    },
    # RED FLAGGED - Suspiciously low prices
    {
        'source': 'Craigslist',
        'title': '2019 Honda CR-V Touring AWD - MUST SELL',
        'price': 11000,  # 48.9% below market
        'mileage': 60000,
        'year': 2019,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://sfbay.craigslist.org/suspicious1',
        'color': 'Red',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.85
    },
    {
        'source': 'Craigslist',
        'title': '2020 Honda CR-V EX-L AWD - Quick Sale',
        'price': 13000,  # ~45% below market
        'mileage': 55000,
        'year': 2020,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://stockton.craigslist.org/suspicious2',
        'color': 'White',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-07',
        'score': 0.80
    },
    {
        'source': 'Cars.com',
        'title': '2018 Mazda CX-5 Grand Touring - Priced to Move',
        'price': 10500,  # Way below market
        'mileage': 70000,
        'year': 2018,
        'make': 'Mazda',
        'model': 'CX-5',
        'url': 'https://cars.com/suspicious3',
        'color': 'Black',
        'region': 'Medford, OR',
        'posted': '2026-03-07',
        'score': 0.78
    },
    # More normal deals
    {
        'source': 'Craigslist',
        'title': '2022 Honda CR-V Sport AWD',
        'price': 26000,
        'mileage': 25000,
        'year': 2022,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://medford.craigslist.org/normal3',
        'color': 'Gray',
        'region': 'Medford, OR',
        'posted': '2026-03-07',
        'score': 0.82
    },
]

print("Testing red flag section layout...")
print("="*70)

# Apply deal scores
for listing in mock_listings:
    listing = apply_deal_score(listing, scorer)

# Count red-flagged vs normal
red_flagged_count = sum(1 for l in mock_listings if (l.get('deal_pct') or 0) >= 45)
normal_count = len(mock_listings) - red_flagged_count

print(f"\n📊 Test Data Summary:")
print(f"   Total listings: {len(mock_listings)}")
print(f"   🚩 Red-flagged (≥45% below): {red_flagged_count}")
print(f"   ✅ Normal deals: {normal_count}")

# Show breakdown
print(f"\n📋 Listing Breakdown:")
for listing in mock_listings:
    deal_pct = listing.get('deal_pct') or 0
    flag = "🚩" if deal_pct >= 45 else "✅"
    grade = listing.get('deal_grade') or 'No data'
    print(f"   {flag} {listing['title'][:50]:50} {grade:15} {deal_pct:5.1f}% below")

# Generate email
results = {
    'San Francisco Bay Area': [l for l in mock_listings if l['region'] == 'San Francisco Bay Area'],
    'Medford, OR': [l for l in mock_listings if l['region'] == 'Medford, OR'],
}

html = build_email_html(results)

# Verify sections exist
checks = {
    'Has TOP PICK section': 'TOP PICK TODAY' in html,
    'Has VERIFY THESE DEALS section': 'VERIFY THESE DEALS' in html,
    'Has ALL LISTINGS BY REGION header': 'ALL LISTINGS BY REGION' in html,
    'Has red flag emoji': '🚩' in html,
    'Has warning text': 'verify carefully for salvage' in html,
}

print("\n" + "="*70)
print("Email Layout Validation:")
print("="*70)
for check, result in checks.items():
    status = "✅" if result else "❌"
    print(f"{status} {check}")

# Count sections
red_flag_section_count = html.count('VERIFY THESE DEALS')
region_header_count = html.count('📍')

print(f"\n📧 Email Structure:")
print(f"   Red flag sections: {red_flag_section_count}")
print(f"   Regional sections: {region_header_count}")
print(f"   Red flag emojis: {html.count('🚩')}")

# Save to file
output_file = 'email_red_flag_section_test.html'
with open(output_file, 'w') as f:
    f.write(html)

print(f"\n✅ Email preview saved to: {output_file}")
print(f"   Open this file in your browser to see the layout:")
print(f"   1. Top Pick section (best deal)")
print(f"   2. Verify These Deals section (red-flagged listings)")
print(f"   3. All Listings by Region (normal listings)")

if all(checks.values()):
    print("\n✅ All layout checks passed!")
else:
    print("\n❌ Some layout checks failed")
