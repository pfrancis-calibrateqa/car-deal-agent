#!/usr/bin/env python3
"""
Test script to intercept Craigslist listing page API calls
and see what data is available for filtering.
"""
import asyncio
import json
from playwright.async_api import async_playwright

async def test_listing_interception():
    url = "https://sacramento.craigslist.org/cto/d/vacaville-2023-mazda-cx-carbon/7917155138.html"
    
    print(f"Testing URL: {url}\n")
    print("="*80)
    
    intercepted_calls = []
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        
        # Intercept all network responses
        async def handle_response(response):
            url = response.url
            status = response.status
            content_type = response.headers.get("content-type", "")
            
            # Log all responses
            print(f"[{status}] {url[:100]}")
            
            # Capture JSON responses
            if "json" in content_type and status == 200:
                try:
                    data = await response.json()
                    intercepted_calls.append({
                        "url": url,
                        "data": data
                    })
                    print(f"  ✓ JSON captured ({len(str(data))} chars)")
                except Exception as e:
                    print(f"  ✗ JSON parse error: {e}")
        
        page.on("response", handle_response)
        
        print("\nNavigating to listing page...\n")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait a bit for any delayed API calls
        await asyncio.sleep(2)
        
        await browser.close()
    
    print("\n" + "="*80)
    print(f"\nCaptured {len(intercepted_calls)} JSON responses\n")
    
    # Analyze captured data
    for i, call in enumerate(intercepted_calls, 1):
        print(f"\n{'='*80}")
        print(f"JSON Response #{i}")
        print(f"URL: {call['url']}")
        print(f"{'='*80}")
        
        data = call['data']
        print(json.dumps(data, indent=2)[:2000])  # First 2000 chars
        
        if len(json.dumps(data)) > 2000:
            print("\n... (truncated, full data below)")
        
        # Look for key fields
        print("\n" + "-"*80)
        print("KEY FIELDS FOUND:")
        print("-"*80)
        
        def find_keys(obj, prefix=""):
            """Recursively find all keys in nested dict"""
            keys = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full_key = f"{prefix}.{k}" if prefix else k
                    keys.append(full_key)
                    if isinstance(v, (dict, list)):
                        keys.extend(find_keys(v, full_key))
            elif isinstance(obj, list) and obj:
                keys.extend(find_keys(obj[0], prefix))
            return keys
        
        all_keys = find_keys(data)
        for key in sorted(set(all_keys)):
            print(f"  - {key}")
        
        # Check for salvage/title keywords
        data_str = json.dumps(data).lower()
        keywords = ["salvage", "rebuilt", "flood", "lemon", "title", "clean title", "accident"]
        found_keywords = [kw for kw in keywords if kw in data_str]
        
        if found_keywords:
            print("\n" + "-"*80)
            print("TITLE/CONDITION KEYWORDS FOUND:")
            print("-"*80)
            for kw in found_keywords:
                print(f"  ✓ '{kw}'")
    
    # Save full data to file for inspection
    if intercepted_calls:
        output_file = "cl_listing_api_data.json"
        with open(output_file, "w") as f:
            json.dump(intercepted_calls, f, indent=2)
        print(f"\n{'='*80}")
        print(f"Full data saved to: {output_file}")
        print(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(test_listing_interception())
