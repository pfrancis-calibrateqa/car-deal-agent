#!/usr/bin/env python3
"""
Test script to extract data from Craigslist listing page HTML
"""
import asyncio
import json
from playwright.async_api import async_playwright

async def test_listing_html():
    url = "https://sacramento.craigslist.org/cto/d/vacaville-2023-mazda-cx-carbon/7917155138.html"
    
    print(f"Testing URL: {url}\n")
    print("="*80)
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Method 1: Check for JSON-LD structured data
        print("\n1. Checking for JSON-LD structured data...")
        json_ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
        print(f"   Found {len(json_ld_scripts)} JSON-LD scripts")
        
        for i, script in enumerate(json_ld_scripts, 1):
            content = await script.inner_html()
            try:
                data = json.loads(content)
                print(f"\n   JSON-LD #{i}:")
                print(json.dumps(data, indent=2)[:1000])
            except:
                pass
        
        # Method 2: Check for embedded JSON in script tags
        print("\n\n2. Checking for embedded JSON in script tags...")
        all_scripts = await page.query_selector_all('script')
        print(f"   Found {len(all_scripts)} total script tags")
        
        for script in all_scripts:
            content = await script.inner_html()
            if 'postingBody' in content or 'attrgroup' in content or 'VIN' in content:
                print(f"\n   Found relevant script content (first 500 chars):")
                print(content[:500])
        
        # Method 3: Extract key fields from HTML
        print("\n\n3. Extracting key fields from HTML...")
        
        # Title
        title_el = await page.query_selector('#titletextonly')
        title = await title_el.inner_text() if title_el else None
        print(f"   Title: {title}")
        
        # Price
        price_el = await page.query_selector('.price')
        price = await price_el.inner_text() if price_el else None
        print(f"   Price: {price}")
        
        # Posting body (description)
        body_el = await page.query_selector('#postingbody')
        body = await body_el.inner_text() if body_el else None
        if body:
            print(f"   Description (first 200 chars): {body[:200]}")
        
        # Attributes (VIN, condition, title status, etc.)
        print("\n   Attributes:")
        attr_groups = await page.query_selector_all('.attrgroup')
        for group in attr_groups:
            attrs = await group.query_selector_all('span')
            for attr in attrs:
                text = await attr.inner_text()
                print(f"     - {text}")
        
        # Check for salvage/title keywords
        page_content = await page.content()
        keywords = ["salvage", "rebuilt", "flood", "lemon", "clean title", "accident"]
        found_keywords = [kw for kw in keywords if kw.lower() in page_content.lower()]
        
        if found_keywords:
            print(f"\n   Keywords found in page: {', '.join(found_keywords)}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_listing_html())
