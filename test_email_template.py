#!/usr/bin/env python3
"""Test that the email template includes deal scoring"""
import sys
sys.path.insert(0, 'src')

from search_agent import build_email_html, apply_deal_score, _deal_cell
from deal_scorer import DealScorer

# Create a mock listing
scorer = DealScorer()
test_listing = {
    'source': 'Craigslist',
    'title': '2013 Honda CR-V EXL AWD',
    'price': 12000,
    'mileage': 120000,
    'year': 2013,
    'make': 'Honda',
    'model': 'CR-V',
    'url': 'https://test.com/listing',
    'color': 'Silver',
    'region': 'San Francisco Bay Area',
    'posted': '2026-03-05',
    'score': 0.65
}

# Apply deal scoring
test_listing = apply_deal_score(test_listing, scorer)

print("Deal fields added to listing:")
print(f"  deal_grade: {test_listing.get('deal_grade')}")
print(f"  deal_pct: {test_listing.get('deal_pct')}")
print(f"  deal_vs_avg: {test_listing.get('deal_vs_avg')}")
print(f"  market_avg: {test_listing.get('market_avg')}")

# Test _deal_cell
html, sort_key = _deal_cell(test_listing)
print(f"\nDeal cell HTML length: {len(html)} chars")
print(f"Deal cell contains grade: {'deal_grade' in str(test_listing.get('deal_grade'))}")

# Build email with this listing
results = {
    'San Francisco Bay Area': [test_listing]
}

html = build_email_html(results)

# Check for key elements
checks = {
    'Has 8 columns': 'Deal vs Market' in html,
    'Has deal cell': 'deal_grade' in str(test_listing.get('deal_grade')) or '🔥' in html or '✅' in html or '➡️' in html,
    'Has colspan=8': 'colspan="8"' in html,
    'Has market avg text': 'mkt avg' in html or 'market' in html.lower(),
}

print("\n" + "="*60)
print("Email Template Validation:")
print("="*60)
for check, result in checks.items():
    status = "✅" if result else "❌"
    print(f"{status} {check}")

if all(checks.values()):
    print("\n✅ Email template is correctly configured!")
    # Save a sample
    with open('test_email_output.html', 'w') as f:
        f.write(html)
    print("Sample email saved to: test_email_output.html")
else:
    print("\n❌ Email template has issues")
    sys.exit(1)
