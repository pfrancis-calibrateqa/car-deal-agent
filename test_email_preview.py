#!/usr/bin/env python3
"""Generate a preview email with mock data to verify the layout"""
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

# Create mock listings with different deal grades
mock_listings = [
    {
        'source': 'Craigslist',
        'title': '2013 Honda CR-V EXL AWD - Great Deal',
        'price': 10000,
        'mileage': 120000,
        'year': 2013,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://sfbay.craigslist.org/test1',
        'color': 'Silver',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-05',
        'score': 0.72
    },
    {
        'source': 'Craigslist',
        'title': '2020 Honda CR-V Touring AWD',
        'price': 23000,
        'mileage': 45000,
        'year': 2020,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://sfbay.craigslist.org/test2',
        'color': 'Blue',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-05',
        'score': 0.65
    },
    {
        'source': 'Craigslist',
        'title': '2023 Mazda CX-5 Carbon Edition',
        'price': 27000,
        'mileage': 21000,
        'year': 2023,
        'make': 'Mazda',
        'model': 'CX-5',
        'url': 'https://sfbay.craigslist.org/test3',
        'color': 'Black',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-05',
        'score': 0.68
    },
    {
        'source': 'Craigslist',
        'title': '2022 Honda CR-V EX AWD Hybrid',
        'price': 21900,
        'mileage': 52000,
        'year': 2022,
        'make': 'Honda',
        'model': 'CR-V',
        'url': 'https://stockton.craigslist.org/test4',
        'color': 'White',
        'region': 'San Francisco Bay Area',
        'posted': '2026-03-05',
        'score': 0.57
    },
]

print("Applying deal scores to mock listings...")
for listing in mock_listings:
    listing = apply_deal_score(listing, scorer)
    print(f"  {listing['title'][:40]:40} -> {listing.get('deal_grade', 'No data')}")

# Build email
results = {
    'San Francisco Bay Area': mock_listings,
    'Medford, OR': []  # Empty region to test that case
}

print("\nGenerating email HTML...")
html = build_email_html(results)

# Save to file
output_file = 'email_preview.html'
with open(output_file, 'w') as f:
    f.write(html)

print(f"\n✅ Email preview saved to: {output_file}")
print(f"   Open this file in your browser to see the layout")

# Verify key elements
checks = {
    'Has 8 columns header': 'Deal vs Market' in html,
    'Has colspan=8': 'colspan="8"' in html,
    'Has deal cell styling': 'min-width:140px' in html,
    'Has market avg text': 'mkt avg' in html,
    'Has region tags': '[SF]' in html or '[MED]' in html,
    'Has grade emojis': any(emoji in html for emoji in ['🔥', '✅', '➡️', '🚫']),
}

print("\n" + "="*60)
print("Email Template Validation:")
print("="*60)
for check, result in checks.items():
    status = "✅" if result else "❌"
    print(f"{status} {check}")

if all(checks.values()):
    print("\n✅ All checks passed! Open email_preview.html to verify visually.")
else:
    print("\n❌ Some checks failed - there may be issues with the template")
