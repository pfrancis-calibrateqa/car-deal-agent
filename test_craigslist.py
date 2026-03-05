#!/usr/bin/env python3
"""
Test Craigslist scraping with detailed logging
"""
import asyncio
import logging
from urllib.parse import urlencode
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

async def test_craigslist():
    # Try different URL formats
    urls_to_test = [
        # Format 1: Old style
        "https://sfbay.craigslist.org/search/cto?" + urlencode({
            "query": "Honda CR-V",
            "min_auto_year": 2012,
            "max_auto_year": 2023,
            "max_auto_miles": 60000,
        }),
        # Format 2: New style with search path
        "https://sfbay.craigslist.org/search/sfc/cto?" + urlencode({
            "query": "Honda CR-V",
            "min_auto_year": 2012,
            "max_auto_year": 2023,
            "max_auto_miles": 60000,
        }),
        # Format 3: Simple search
        "https://sfbay.craigslist.org/search/cta?query=Honda+CR-V",
    ]
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        
        for idx, url in enumerate(urls_to_test):
            log.info(f"\n{'='*60}")
            log.info(f"Test {idx+1}: {url}")
            log.info(f"{'='*60}")
            
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(2)
                
                # Check for listing cards with multiple selectors
                selectors = [
                    "li.cl-static-search-result",
                    "li.result-row",
                    ".result-info",
                    "[data-pid]",
                ]
                
                for selector in selectors:
                    cards = await page.query_selector_all(selector)
                    if cards:
                        log.info(f"✓ Found {len(cards)} listings with selector: {selector}")
                        
                        # Show first listing
                        if len(cards) > 0:
                            first_card = cards[0]
                            html = await first_card.inner_html()
                            log.info(f"First listing HTML: {html[:300]}")
                        break
                else:
                    log.warning("No listings found with any selector")
                
                # Check page text
                body_text = await page.evaluate("() => document.body.innerText")
                if "no results" in body_text.lower():
                    log.warning("Page says 'no results'")
                else:
                    log.info("Page does not say 'no results'")
                
            except Exception as e:
                log.error(f"Error: {e}")
            finally:
                await page.close()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_craigslist())
