#!/usr/bin/env python3
import asyncio
from urllib.parse import urlencode
from playwright.async_api import async_playwright

async def debug():
    url = "https://sfbay.craigslist.org/search/cta?" + urlencode({
        "query": "Honda CR-V",
        "min_auto_year": 2012,
        "max_auto_year": 2023,
        "max_auto_miles": 70000,
        "purveyor": "owner",
    })
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Get first card HTML
        cards = await page.query_selector_all("[data-pid]")
        if cards:
            html = await cards[0].inner_html()
            print("First card HTML:")
            print(html[:2000])
            print("\n" + "="*60 + "\n")
            
            # Try to find title in different ways
            link = await cards[0].query_selector("a.main")
            if link:
                print("Link found!")
                print(f"href: {await link.get_attribute('href')}")
                print(f"title attr: {await link.get_attribute('title')}")
                print(f"inner_text: '{await link.inner_text()}'")
                print(f"text_content: '{await link.text_content()}'")
                
                # Check for aria-label
                aria = await link.get_attribute("aria-label")
                print(f"aria-label: {aria}")
        
        await browser.close()

asyncio.run(debug())
