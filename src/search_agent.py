#!/usr/bin/env python3
"""
Car Search Agent — Playwright Edition
======================================
Uses Playwright with network interception as the primary extraction strategy.
Rather than parsing HTML, we intercept XHR/fetch calls the page makes to its
own backend APIs and extract clean JSON directly — far more reliable than
CSS selectors which break whenever a site redesigns.

Sources: Craigslist, AutoTrader, Cars.com

Fixes applied:
  - santacruz -> monterey (valid CL subdomain)
  - Cars.com: domcontentloaded instead of networkidle to avoid timeout
  - AutoTrader: domcontentloaded instead of networkidle
  - Craigslist: added random delay + realistic headers to avoid bot detection
  - Cars.com: disabled HTTP/2 via context arg to avoid ERR_HTTP2_PROTOCOL_ERROR

v2 additions:
  - Market value comparison via DealScorer (MarketCheck API + local cache)
  - Deal grade + savings vs market added to each listing
  - Email now includes Deal column with grade emoji and % vs market
  - Regional flag added: listings note SF Bay Area vs Medford in deal context
"""

import os
import re
import json
import asyncio
import smtplib
import hashlib
import logging
import random
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlencode, quote_plus

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

# ── Deal scoring integration ──────────────────────────────────────────────────
# DealScorer lives in the same src/ directory as this file.
# It reads from car_values_cache.json (same directory) and falls back to a
# live MarketCheck API call when a vehicle isn't cached yet.
from deal_scorer import DealScorer, ScrapedListing

# Load environment variables from .env file
load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Paths & env ───────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config" / "search_criteria.json"
SEEN_FILE   = ROOT / "data" / "seen_listings.json"

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_TO  = os.environ["NOTIFY_EMAIL"]

# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_seen() -> set:
    SEEN_FILE.parent.mkdir(exist_ok=True)
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def listing_id(listing: dict) -> str:
    return hashlib.md5(listing["url"].encode()).hexdigest()


# ── Scoring & filtering ───────────────────────────────────────────────────────

def value_score(listing: dict, config: dict) -> float:
    """
    Composite score — higher = better deal.
      year_score    40%  (newer reliable year -> higher)
      mileage_score 40%  (fewer miles -> higher)
      price_score   20%  (lower price relative to $50k soft ceiling -> higher)
    """
    all_years = [y for s in config["searches"] for y in s["years"]]
    min_y, max_y = min(all_years), max(all_years)

    year   = listing.get("year") or min_y
    miles  = listing.get("mileage") or config["filters"]["max_mileage"]
    price  = listing.get("price") or 50_000

    year_score    = (year - min_y) / max(max_y - min_y, 1)
    mileage_score = max(0.0, 1 - miles / config["filters"]["max_mileage"])
    price_score   = max(0.0, 1 - price / 50_000)

    return round(year_score * 0.40 + mileage_score * 0.40 + price_score * 0.20, 4)


def passes_filters(listing: dict, config: dict) -> bool:
    f = config["filters"]

    # Mileage hard cap
    if (listing.get("mileage") or 999_999) > f["max_mileage"]:
        return False

    # Must be a valid year for this make/model
    valid_years = {
        y
        for s in config["searches"]
        if s["make"] == listing.get("make") and s["model"] == listing.get("model")
        for y in s["years"]
    }
    if valid_years and listing.get("year") not in valid_years:
        return False

    # Exclude red-flag keywords in title + description
    text = (listing.get("title", "") + " " + listing.get("description", "")).lower()
    if any(kw in text for kw in f["exclude_keywords"]):
        return False

    # Color filter (soft — skip check if no color info present)
    color = (listing.get("color") or "").lower()
    if color and any(c in color for c in f["exclude_colors"]):
        return False

    return True


# ── Market value scoring ──────────────────────────────────────────────────────

# Region label → short tag shown in the email Deal column
REGION_TAGS = {
    "San Francisco Bay Area": "SF",
    "Medford, OR":            "MED",
}

def apply_deal_score(listing: dict, scorer: DealScorer) -> dict:
    """
    Runs the listing through DealScorer and attaches three new fields:
      deal_grade   str   e.g. "🔥 Steal"
      deal_pct     float e.g. 18.4  (positive = below market, negative = above)
      deal_vs_avg  int   e.g. -4200 (negative = you save, positive = you overpay)
      market_avg   int   e.g. 27900
      deal_data_src str  "cache" or "live_api"

    If no market data is found (new/rare vehicle, API down, no key set),
    all deal fields are set to None so the email degrades gracefully.
    """
    if not listing.get("price") or not listing.get("year"):
        listing.update({"deal_grade": None, "deal_pct": None,
                        "deal_vs_avg": None, "market_avg": None,
                        "deal_data_src": None})
        return listing

    scraped = ScrapedListing(
        asking_price = listing["price"],
        year         = listing["year"],
        make         = listing["make"],
        model        = listing["model"],
        mileage      = listing.get("mileage"),
        trim         = listing.get("trim"),          # None if not scraped
        condition    = listing.get("condition"),     # None if not scraped
        source_url   = listing.get("url"),
        source_site  = listing.get("source", "").lower().replace(" ", "_"),
    )

    result = scorer.score(scraped)

    if result:
        listing["deal_grade"]    = result.grade
        listing["deal_pct"]      = result.pct_below_market
        listing["deal_vs_avg"]   = int(result.savings_vs_avg)
        listing["market_avg"]    = int(result.market_avg)
        listing["deal_data_src"] = result.data_source
    else:
        listing["deal_grade"]    = None
        listing["deal_pct"]      = None
        listing["deal_vs_avg"]   = None
        listing["market_avg"]    = None
        listing["deal_data_src"] = None

    return listing


# ── Utility parsers ───────────────────────────────────────────────────────────

def extract_year(text: str):
    m = re.search(r"\b(20[012]\d|199\d)\b", str(text))
    return int(m.group()) if m else None


def extract_mileage(text: str):
    if not text:
        return None
    text = str(text).replace(",", "")
    m = re.search(r"([\d]+)\s*(?:k|mi|miles)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if val < 1_000 and "k" in text.lower():
            val *= 1_000
        return val if val < 500_000 else None
    m = re.search(r"odometer[:\s]+(\d+)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return val if val < 500_000 else None
    return None


def extract_price(text: str):
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


# ── Browser factory ───────────────────────────────────────────────────────────

async def make_browser(playwright):
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-http2",
        ],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/Los_Angeles",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


async def human_delay(min_ms: int = 1500, max_ms: int = 3500):
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


# ── Deep Inspection ───────────────────────────────────────────────────────────

async def deep_inspect_listing(page: Page, listing: dict) -> dict:
    """
    Visit a listing URL and extract detailed information including title status.
    Returns the listing dict with added fields: title_status, detailed_condition.
    Returns None if the listing should be filtered out (salvage, etc.).
    """
    url = listing.get("url")
    if not url:
        return listing
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        await asyncio.sleep(0.5)  # Brief pause for content to render
        
        # Extract title status and transmission from attributes
        title_status = None
        transmission = None
        attr_groups = await page.query_selector_all('.attrgroup')
        for group in attr_groups:
            spans = await group.query_selector_all('span')
            for i, span in enumerate(spans):
                text = await span.inner_text()
                if 'title status:' in text.lower():
                    # Next span should have the value
                    if i + 1 < len(spans):
                        status_span = spans[i + 1]
                        title_status = (await status_span.inner_text()).strip()
                elif 'transmission:' in text.lower():
                    # Next span should have the value
                    if i + 1 < len(spans):
                        trans_span = spans[i + 1]
                        transmission = (await trans_span.inner_text()).strip()
        
        # Extract full description
        body_el = await page.query_selector('#postingbody')
        description = (await body_el.inner_text()).strip() if body_el else ""
        
        # Check for manual transmission (filter out manual, keep automatic)
        if transmission and 'manual' in transmission.lower():
            log.info(f"  ⚠️  Filtered out (manual transmission): {listing.get('title', '')[:50]}")
            return None
        
        # Check for red flags in title status and description
        red_flags = ["salvage", "rebuilt", "flood", "lemon", "branded"]
        combined_text = f"{title_status or ''} {description}".lower()
        
        has_red_flag = any(flag in combined_text for flag in red_flags)
        
        if has_red_flag:
            log.info(f"  ⚠️  Filtered out (title issue): {listing.get('title', '')[:50]}")
            return None
        
        # Check for non-running vehicle phrases
        non_running_phrases = ["won't start", "wont start", "doesn't start", "doesnt start", "does not start", "will not start"]
        has_non_running = any(phrase in combined_text for phrase in non_running_phrases)
        
        if has_non_running:
            log.info(f"  ⚠️  Filtered out (won't start): {listing.get('title', '')[:50]}")
            return None
        
        # Add extracted data to listing
        listing["title_status"] = title_status
        listing["transmission"] = transmission
        listing["full_description"] = description[:500]  # First 500 chars
        
        return listing
        
    except Exception as e:
        log.warning(f"  Deep inspection failed for {url[:50]}: {e}")
        # On error, return the listing (don't filter it out due to inspection failure)
        return listing


async def deep_inspect_listings(context, listings: list[dict], concurrency: int = 5) -> list[dict]:
    """
    Concurrently inspect multiple listings for detailed information.
    Returns filtered list with only clean-title vehicles.
    """
    if not listings:
        return []
    
    log.info(f"\n🔍 Deep inspecting {len(listings)} listings (checking title status)...")
    
    inspected = []
    
    # Process in batches for concurrency control
    for i in range(0, len(listings), concurrency):
        batch = listings[i:i + concurrency]
        
        async def inspect_one(listing):
            page = await context.new_page()
            try:
                result = await deep_inspect_listing(page, listing)
                return result
            finally:
                await page.close()
                await human_delay(500, 1000)  # Small delay between requests
        
        # Process batch concurrently
        results = await asyncio.gather(*[inspect_one(l) for l in batch], return_exceptions=True)
        
        # Filter out None results (filtered listings) and exceptions
        for result in results:
            if result is not None and not isinstance(result, Exception):
                inspected.append(result)
    
    filtered_count = len(listings) - len(inspected)
    if filtered_count > 0:
        log.info(f"  ✓ Filtered out {filtered_count} listings (title/transmission/condition issues)")
    log.info(f"  ✓ {len(inspected)} clean listings remaining")
    
    return inspected


# ══════════════════════════════════════════════════════════════════════════════
#  CRAIGSLIST
# ══════════════════════════════════════════════════════════════════════════════

CL_SUBDOMAINS = {
    "San Francisco Bay Area": ["sfbay", "sacramento", "stockton", "modesto", "monterey"],
    "Medford, OR":            ["medford", "eugene", "bend", "roseburg"],
}


async def search_craigslist(context, make: str, model: str, years: list, region: dict, config: dict) -> list:
    listings = []
    sites = CL_SUBDOMAINS.get(region["name"], ["sfbay"])
    min_year, max_year = min(years), max(years)
    max_mileage = config["filters"]["max_mileage"]

    for site in sites:
        params = urlencode({
            "query":           f"{make} {model}",
            "min_auto_year":   min_year,
            "max_auto_year":   max_year,
            "max_auto_miles":  max_mileage,
            "purveyor":        "owner",
            "s":               0,
        })
        url = f"https://{site}.craigslist.org/search/cta?{params}"

        page: Page = await context.new_page()
        try:
            log.debug(f"  Craigslist URL: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await human_delay(2000, 4000)

            json_data = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script[type="application/json"]');
                    for (const s of scripts) {
                        try { return JSON.parse(s.textContent); } catch(e) {}
                    }
                    return null;
                }
            """)

            site_listings = []

            if json_data:
                items = []
                if isinstance(json_data, dict):
                    items = json_data.get("items", json_data.get("data", {}).get("items", []))
                elif isinstance(json_data, list):
                    items = json_data
                for item in items:
                    title = item.get("Title") or item.get("title") or ""
                    price = extract_price(item.get("Ask") or item.get("price") or "")
                    href  = item.get("PostingURL") or item.get("url") or ""
                    if title and href:
                        site_listings.append(_cl_listing(title, price, href, make, model, region))

            if not site_listings:
                cards = await page.query_selector_all("[data-pid]")
                log.info(f"  Found {len(cards)} cards with [data-pid] selector")
                for card in cards:
                    link_el = await card.query_selector("a[href*='/cto/'], a[href*='/ctd/']")
                    if not link_el:
                        continue
                    href = await link_el.get_attribute("href")
                    if not href:
                        continue
                    title_text = None
                    label_span = await card.query_selector("span.label")
                    if label_span:
                        title_text = (await label_span.inner_text()).strip()
                    if not title_text:
                        title_el = await card.query_selector(".posting-title")
                        if title_el:
                            title_text = (await title_el.inner_text()).strip()
                    if not title_text:
                        match = re.search(r'/d/([^/]+)/', href)
                        if match:
                            title_text = match.group(1).replace('-', ' ').title()
                    price_el = await card.query_selector(".price, .priceinfo")
                    price_text = (await price_el.inner_text()).strip() if price_el else ""
                    mileage_text = None
                    meta_el = await card.query_selector(".meta, .meta-line .meta")
                    if meta_el:
                        mileage_text = (await meta_el.inner_text()).strip()
                    if title_text and href:
                        listing = _cl_listing(title_text, extract_price(price_text), href, make, model, region)
                        if mileage_text:
                            listing["mileage"] = extract_mileage(mileage_text)
                        site_listings.append(listing)

            listings.extend(site_listings)
            log.info(f"  Craigslist [{site}]: {len(site_listings)} listings")

        except Exception as e:
            log.warning(f"  Craigslist [{site}] error: {e}")
        finally:
            await page.close()
            await human_delay(500, 1500)

    return listings


def _cl_listing(title, price, url, make, model, region) -> dict:
    return {
        "source":      "Craigslist",
        "title":       title,
        "price":       price,
        "mileage":     extract_mileage(title),
        "year":        extract_year(title),
        "make":        make,
        "model":       model,
        "url":         url,
        "color":       "",
        "description": title,
        "region":      region["name"],
        "posted":      date.today().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  AUTOTRADER
# ══════════════════════════════════════════════════════════════════════════════

async def search_autotrader(context, make: str, model: str, years: list, region: dict) -> list:
    listings = []
    intercepted_listings: list[dict] = []
    zip_code = region["center_zip"]
    radius   = region["radius_miles"]

    params = urlencode({
        "makeCodeList":  make.upper(),
        "modelCodeList": model.upper().replace("-", "_").replace(" ", "_"),
        "startYear":     min(years),
        "endYear":       max(years),
        "listingTypes":  "PRIVATE",
        "driveGroup":    "AWD4WD",
        "maxMileage":    70000,
        "zip":           zip_code,
        "searchRadius":  radius,
        "sortBy":        "derivedpriceASC",
        "numRecords":    100,
    })
    url = (
        f"https://www.autotrader.com/cars-for-sale/used-cars"
        f"/{quote_plus(make.lower())}/{quote_plus(model.lower())}"
        f"/{zip_code}?{params}"
    )

    page: Page = await context.new_page()
    try:
        async def handle_response(response):
            if (
                ("listing" in response.url.lower() or "lsc" in response.url.lower())
                and response.status == 200
            ):
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        data = await response.json()
                        items = (
                            data.get("listings")
                            or data.get("data", {}).get("listings", [])
                            or []
                        )
                        if items:
                            intercepted_listings.extend(items)
                            log.info(f"  AutoTrader intercepted {len(items)} listings from API")
                    except Exception:
                        pass

        page.on("response", handle_response)
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await human_delay(3000, 5000)

        for item in intercepted_listings:
            price   = extract_price(str(
                item.get("pricingDetail", {}).get("salePrice", "")
                or item.get("price", "")
            ))
            mileage = item.get("mileage") or extract_mileage(
                str(item.get("specifications", {}).get("mileage", ""))
            )
            year    = item.get("year") or extract_year(item.get("title", ""))
            color_raw = item.get("exteriorColor", "")
            color   = color_raw.get("name", "") if isinstance(color_raw, dict) else color_raw
            title   = item.get("title") or f"{year} {make} {model}"
            href    = item.get("link") or item.get("url") or ""
            if href and not href.startswith("http"):
                href = "https://www.autotrader.com" + href

            listings.append({
                "source":      "AutoTrader",
                "title":       title,
                "price":       extract_price(str(price)) if price else None,
                "mileage":     int(mileage) if mileage else None,
                "year":        int(year) if year else None,
                "make":        make,
                "model":       model,
                "url":         href,
                "color":       color,
                "description": item.get("description", ""),
                "region":      region["name"],
                "posted":      date.today().isoformat(),
            })

        if not intercepted_listings:
            log.info("  AutoTrader: no intercepted JSON, falling back to DOM")
            cards = await page.query_selector_all(
                "[data-cmp='listingCard'], [data-listing-id]"
            )
            for card in cards:
                title_el = await card.query_selector("[data-cmp='listingTitle'], h2, h3")
                price_el = await card.query_selector("[data-cmp='firstPrice'], [class*='price']")
                miles_el = await card.query_selector("[data-cmp='mileage'], [class*='mileage']")
                link_el  = await card.query_selector("a[href]")
                if not title_el:
                    continue
                title      = (await title_el.inner_text()).strip()
                price_text = (await price_el.inner_text()).strip() if price_el else ""
                miles_text = (await miles_el.inner_text()).strip() if miles_el else ""
                href       = await link_el.get_attribute("href") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.autotrader.com" + href
                if title and href:
                    listings.append({
                        "source":      "AutoTrader",
                        "title":       title,
                        "price":       extract_price(price_text),
                        "mileage":     extract_mileage(miles_text),
                        "year":        extract_year(title),
                        "make":        make,
                        "model":       model,
                        "url":         href,
                        "color":       "",
                        "description": title,
                        "region":      region["name"],
                        "posted":      date.today().isoformat(),
                    })

        log.info(f"  AutoTrader total: {len(listings)} listings")

    except Exception as e:
        log.warning(f"  AutoTrader error ({make} {model}): {e}")
    finally:
        await page.close()

    return listings


# ══════════════════════════════════════════════════════════════════════════════
#  CARS.COM
# ══════════════════════════════════════════════════════════════════════════════

async def search_cars_dot_com(context, make: str, model: str, years: list, region: dict) -> list:
    listings = []
    intercepted_listings: list[dict] = []
    zip_code   = region["center_zip"]
    radius     = region["radius_miles"]
    make_slug  = make.lower()
    model_slug = model.lower().replace(" ", "-")

    params = urlencode({
        "makes[]":          make_slug,
        "models[]":         f"{make_slug}-{model_slug}",
        "year_min":         min(years),
        "year_max":         max(years),
        "mileage_max":      70000,
        "maximum_distance": radius,
        "seller_types[]":   "private_seller",
        "stock_type":       "used",
        "zip":              zip_code,
        "sort":             "best_match_desc",
    })
    url = f"https://www.cars.com/shopping/results/?{params}"

    page: Page = await context.new_page()
    try:
        async def handle_response(response):
            if "shopping" in response.url and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        data = await response.json()
                        items = data.get("data", []) or data.get("listings", [])
                        if items:
                            intercepted_listings.extend(items)
                            log.info(f"  Cars.com intercepted {len(items)} listings from API")
                    except Exception:
                        pass

        page.on("response", handle_response)
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await human_delay(3000, 5000)

        for item in intercepted_listings:
            price   = extract_price(str(item.get("list_price") or item.get("price") or ""))
            mileage = item.get("mileage") or extract_mileage(str(item.get("miles", "")))
            year    = item.get("year") or extract_year(item.get("name", ""))
            color   = item.get("exterior_color") or item.get("color") or ""
            title   = item.get("name") or item.get("title") or f"{year} {make} {model}"
            slug    = item.get("url_slug") or item.get("url") or ""
            href    = f"https://www.cars.com{slug}" if slug.startswith("/") else slug
            if title and href:
                listings.append({
                    "source":      "Cars.com",
                    "title":       title,
                    "price":       price,
                    "mileage":     int(mileage) if mileage else None,
                    "year":        int(year) if year else None,
                    "make":        make,
                    "model":       model,
                    "url":         href,
                    "color":       color,
                    "description": item.get("description", ""),
                    "region":      region["name"],
                    "posted":      date.today().isoformat(),
                })

        if not intercepted_listings:
            log.info("  Cars.com: trying JSON-LD extraction")
            ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in ld_scripts:
                try:
                    raw  = await script.inner_html()
                    data = json.loads(raw)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get("@type") not in ("Car", "Vehicle"):
                            continue
                        offer  = item.get("offers", {})
                        price  = extract_price(str(offer.get("price", "")))
                        year   = item.get("vehicleModelDate") or extract_year(item.get("name", ""))
                        color  = item.get("color", "")
                        title  = item.get("name", f"{year} {make} {model}")
                        miles  = extract_mileage(
                            str(item.get("mileageFromOdometer", {}).get("value", ""))
                        )
                        href   = item.get("url") or offer.get("url") or url
                        if title and href:
                            listings.append({
                                "source":      "Cars.com",
                                "title":       title,
                                "price":       price,
                                "mileage":     miles,
                                "year":        int(year) if year else None,
                                "make":        make,
                                "model":       model,
                                "url":         href,
                                "color":       color,
                                "description": item.get("description", ""),
                                "region":      region["name"],
                                "posted":      date.today().isoformat(),
                            })
                except Exception:
                    pass

        if not listings:
            log.info("  Cars.com: falling back to DOM")
            cards = await page.query_selector_all(
                "cars-listing-card, .vehicle-card, [data-listing-id]"
            )
            for card in cards:
                title_el = await card.query_selector(".title, h2, [class*='title']")
                price_el = await card.query_selector(".primary-price, [class*='price']")
                miles_el = await card.query_selector(".mileage, [class*='mileage']")
                link_el  = await card.query_selector("a[href]")
                if not title_el:
                    continue
                title      = (await title_el.inner_text()).strip()
                price_text = (await price_el.inner_text()).strip() if price_el else ""
                miles_text = (await miles_el.inner_text()).strip() if miles_el else ""
                href       = await link_el.get_attribute("href") if link_el else ""
                if href and href.startswith("/"):
                    href = "https://www.cars.com" + href
                if title and href:
                    listings.append({
                        "source":      "Cars.com",
                        "title":       title,
                        "price":       extract_price(price_text),
                        "mileage":     extract_mileage(miles_text),
                        "year":        extract_year(title),
                        "make":        make,
                        "model":       model,
                        "url":         href,
                        "color":       "",
                        "description": title,
                        "region":      region["name"],
                        "posted":      date.today().isoformat(),
                    })

        log.info(f"  Cars.com total: {len(listings)} listings")

    except Exception as e:
        log.warning(f"  Cars.com error ({make} {model}): {e}")
    finally:
        await page.close()

    return listings


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def _deal_cell(listing: dict) -> tuple[str, str]:
    """
    Returns (cell_html, sort_key) for the Deal column.

    Layout inside the cell:
      Line 1 — grade emoji + label          e.g. "🔥 Steal"
      Line 2 — % vs market + region tag     e.g. "18.4% below  [SF]"
      Line 3 — savings dollar amount        e.g. "save $4,200"

    If no market data is available, shows a neutral "—" placeholder.
    """
    grade    = listing.get("deal_grade")
    pct      = listing.get("deal_pct")        # positive = below market (good)
    vs_avg   = listing.get("deal_vs_avg")     # negative = you save (good)
    mkt_avg  = listing.get("market_avg")
    region   = listing.get("region", "")
    region_tag = REGION_TAGS.get(region, region[:3].upper())

    if grade is None or pct is None:
        return (
            '<span style="color:#475569;font-size:12px;">— no data</span>',
            -999
        )

    # Colour the percentage line: green = good deal, amber = fair, red = over
    if pct >= 10:
        pct_color = "#22c55e"
    elif pct >= 0:
        pct_color = "#f59e0b"
    else:
        pct_color = "#ef4444"

    direction  = "below" if pct >= 0 else "above"
    pct_str    = f"{abs(pct):.1f}% {direction}"

    # Savings line
    if vs_avg is not None:
        if vs_avg < 0:
            savings_str = f"save ${abs(vs_avg):,}"
            savings_color = "#22c55e"
        else:
            savings_str = f"${vs_avg:,} over"
            savings_color = "#ef4444"
    else:
        savings_str   = ""
        savings_color = "#94a3b8"

    mkt_str = f"mkt avg ${mkt_avg:,}" if mkt_avg else ""

    cell_html = f"""
        <span style="font-size:12px;font-weight:700;color:#f1f5f9;">{grade}</span><br>
        <span style="font-size:11px;color:{pct_color};">{pct_str}</span>
        <span style="font-size:10px;color:#475569;margin-left:4px;">[{region_tag}]</span><br>
        <span style="font-size:11px;color:{savings_color};">{savings_str}</span>
        <span style="font-size:10px;color:#334155;margin-left:4px;">{mkt_str}</span>
    """
    return cell_html, pct   # sort key = pct_below_market


def build_email_html(results_by_region: dict) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    rows_html = ""

    for region_name, listings in results_by_region.items():
        rows_html += f"""
        <tr>
          <td colspan="8" style="background:#1a1a2e;color:#e2e8f0;padding:12px 18px;
              font-size:14px;font-weight:700;letter-spacing:0.06em;
              border-top:2px solid #3b4fd8;">
            📍 {region_name}
          </td>
        </tr>"""

        if not listings:
            rows_html += """
        <tr>
          <td colspan="8" style="padding:14px 18px;color:#64748b;font-style:italic;">
            No new listings found today.
          </td>
        </tr>"""
        else:
            for i, l in enumerate(listings, 1):
                score_pct   = int(l["score"] * 100)
                score_color = (
                    "#22c55e" if score_pct >= 65
                    else "#f59e0b" if score_pct >= 40
                    else "#ef4444"
                )
                mileage_str  = f"{l['mileage']:,}" if l.get("mileage") else "—"
                price_str    = f"${l['price']:,}" if l.get("price") else "—"
                color_str    = l.get("color") or "—"
                row_bg       = "#0f172a" if i % 2 == 0 else "#1e293b"
                deal_html, _ = _deal_cell(l)

                rows_html += f"""
        <tr style="background:{row_bg};">
          <td style="padding:10px 10px;font-weight:700;color:#94a3b8;
                     font-size:13px;text-align:center;width:32px;">{i}</td>
          <td style="padding:10px 12px;min-width:200px;">
            <a href="{l['url']}" style="color:#60a5fa;text-decoration:none;
               font-weight:600;font-size:13px;">{l['title'][:60]}</a><br>
            <span style="font-size:11px;color:#475569;">{l['source']}</span>
          </td>
          <td style="padding:10px 10px;color:#f1f5f9;font-weight:600;
                     white-space:nowrap;">{price_str}</td>
          <td style="padding:10px 10px;color:#cbd5e1;white-space:nowrap;">{mileage_str} mi</td>
          <td style="padding:10px 10px;color:#94a3b8;font-size:12px;">{color_str}</td>
          <td style="padding:10px 12px;min-width:160px;">{deal_html}</td>
          <td style="padding:10px 10px;text-align:center;white-space:nowrap;">
            <span style="background:{score_color}20;color:{score_color};
                padding:3px 9px;border-radius:20px;font-size:12px;
                font-weight:800;letter-spacing:0.03em;">{score_pct}</span>
          </td>
          <td style="padding:10px 10px;color:#475569;font-size:11px;
                     white-space:nowrap;">{l.get('posted','')}</td>
        </tr>"""

    # 8 columns now (added Deal)
    col_headers = ["#", "Listing", "Price", "Miles", "Color", "Deal vs Market", "Score", "Posted"]
    col_html = "".join(
        f'<td style="padding:9px 12px;color:#334155;font-size:10px;'
        f'text-transform:uppercase;letter-spacing:0.1em;font-weight:700;">{h}</td>'
        for h in col_headers
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#080f1a;font-family:'Segoe UI',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:32px 16px;">
  <table width="960" cellpadding="0" cellspacing="0"
         style="border-radius:14px;overflow:hidden;border:1px solid #1e293b;
                box-shadow:0 20px 60px rgba(0,0,0,0.6);">

    <tr>
      <td colspan="8"
          style="background:linear-gradient(135deg,#0f2744 0%,#1a1a2e 100%);
                 padding:28px 24px;border-bottom:1px solid #1e3a5f;">
        <div style="font-size:24px;font-weight:900;color:#f1f5f9;
                    letter-spacing:-0.03em;">🚗 Daily Car Deal Digest</div>
        <div style="font-size:12px;color:#475569;margin-top:6px;letter-spacing:0.04em;">
          {today} &nbsp;·&nbsp; Honda CR-V &amp; Mazda CX-5
          &nbsp;·&nbsp; AWD &nbsp;·&nbsp; Private Party &nbsp;·&nbsp; &lt;70,000 mi
          &nbsp;·&nbsp; Deal scores vs national market avg
        </div>
      </td>
    </tr>

    <tr style="background:#0b1526;border-bottom:1px solid #1e293b;">
      {col_html}
    </tr>

    {rows_html}

    <tr>
      <td colspan="8"
          style="background:#080f1a;padding:14px 24px;
                 color:#1e293b;font-size:11px;border-top:1px solid #0f172a;">
        Score: year 40% · mileage 40% · price 20%
        &nbsp;|&nbsp; Green ≥65 · Yellow ≥40 · Red &lt;40
        &nbsp;|&nbsp; Deal vs Market: MarketCheck national avg (mileage-adjusted)
        &nbsp;|&nbsp; [SF] = Bay Area listing · [MED] = Medford listing
        &nbsp;·&nbsp; SF prices typically run higher than national avg
        &nbsp;|&nbsp; New listings only · Powered by Playwright
      </td>
    </tr>

  </table>
  </td></tr>
  </table>
</body>
</html>"""


def send_email(subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_TO
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_USER, GMAIL_PASS)
        srv.sendmail(GMAIL_USER, NOTIFY_TO, msg.as_string())
    log.info(f"Email sent to {NOTIFY_TO}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def run():
    config   = load_config()
    seen     = load_seen()
    current_live_hashes: set = set()  # All listings found in this search run
    new_listings_to_notify: set = set()  # New listings to email about
    results_by_region: dict = {}

    # One scorer instance shared across all listings — it holds the cache
    # in memory and reuses it, so each unique vehicle is only fetched once
    # even if multiple listings match the same make/model/year.
    scorer = DealScorer()

    async with async_playwright() as pw:
        browser, context = await make_browser(pw)
        try:
            for region in config["regions"]:
                log.info(f"\n{'='*60}")
                log.info(f"Region: {region['name']}")
                log.info(f"{'='*60}")
                region_listings = []

                for search in config["searches"]:
                    make  = search["make"]
                    model = search["model"]
                    years = search["years"]
                    log.info(f"\n-> {make} {model} ({min(years)}-{max(years)})")

                    raw: list[dict] = []
                    raw += await search_craigslist(context, make, model, years, region, config)
                    raw += await search_autotrader(context, make, model, years, region)
                    raw += await search_cars_dot_com(context, make, model, years, region)

                    for listing in raw:
                        lid = listing_id(listing)
                        current_live_hashes.add(lid)  # Track all live listings
                        
                        if lid in seen:
                            continue  # Already notified, skip
                        if lid in new_listings_to_notify:
                            continue  # Already added to this batch
                        if not listing.get("url"):
                            continue
                        if not passes_filters(listing, config):
                            continue

                        # ── Existing value score (unchanged) ──
                        listing["score"] = value_score(listing, config)

                        # ── NEW: market deal score ──────────────
                        listing = apply_deal_score(listing, scorer)

                        region_listings.append(listing)
                        new_listings_to_notify.add(lid)

                region_listings.sort(key=lambda x: x["score"], reverse=True)
                
                # ── Deep inspection: check title status on listing pages ──
                if region_listings:
                    region_listings = await deep_inspect_listings(context, region_listings, concurrency=5)
                
                results_by_region[region["name"]] = region_listings[:25]
                log.info(f"\n✓ {region['name']}: {len(region_listings)} qualifying new listings")

        finally:
            await context.close()
            await browser.close()

    # Update seen_listings: only keep currently live listings
    # This automatically removes sold/expired listings
    save_seen(current_live_hashes)
    
    removed_count = len(seen - current_live_hashes)
    if removed_count > 0:
        log.info(f"\n🗑️  Removed {removed_count} sold/expired listings from tracking")

    api_stats = scorer.stats()
    log.info(
        f"\nDeal scorer: {api_stats['scored']} listings scored  |  "
        f"{api_stats['live_api_calls']} live MarketCheck API calls made"
    )

    total   = sum(len(v) for v in results_by_region.values())
    subject = f"🚗 Car Deal Digest — {total} new listings · {date.today().strftime('%b %d')}"
    html    = build_email_html(results_by_region)
    send_email(subject, html)
    log.info(f"\nDone. {total} new listings delivered.")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()