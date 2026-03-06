#!/usr/bin/env python3
"""Test the deep inspection feature"""
import sys
import asyncio
sys.path.insert(0, 'src')

from playwright.async_api import async_playwright
from search_agent import make_browser, deep_inspect_listings

async def test():
    # Test listings - mix of clean and potentially problematic
    test_listings = [
        {
            "title": "2023 Mazda CX-5 Carbon",
            "url": "https://sacramento.craigslist.org/cto/d/vacaville-2023-mazda-cx-carbon/7917155138.html",
            "price": 27000,
            "year": 2023,
            "make": "Mazda",
            "model": "CX-5",
            "score": 0.75
        }
    ]
    
    print("Testing deep inspection on 1 listing...\n")
    
    async with async_playwright() as pw:
        browser, context = await make_browser(pw)
        try:
            results = await deep_inspect_listings(context, test_listings, concurrency=1)
            
            print("\n" + "="*80)
            print("RESULTS:")
            print("="*80)
            
            for listing in results:
                print(f"\nTitle: {listing['title']}")
                print(f"URL: {listing['url']}")
                print(f"Title Status: {listing.get('title_status', 'N/A')}")
                print(f"Description: {listing.get('full_description', 'N/A')[:100]}...")
            
            print(f"\n✓ {len(results)} listings passed inspection")
            
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
