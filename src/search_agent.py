#!/usr/bin/env python3
"""
Car Search Agent — Playwright Edition
======================================
Uses Playwright with network interception as the primary extraction strategy.
Rather than parsing HTML, we intercept XHR/fetch calls the page makes to its
own backend APIs and extract clean JSON directly — far more reliable than
CSS selectors which break whenever a site redesigns.

Sources: Craigslist, AutoTrader, Cars.com
"""

import os
import re
import json
import asyncio
import smtplib
import hashlib
import logging
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlencode, quote_plus

from playwright.async_api import async_playwright, Page

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


# ── Utility parsers ───────────────────────────────────────────────────────────

def extract_year(text: str) -> int | None:
    m = re.search(r"\b(20[012]\d|199\d)\b", str(text))
    return int(m.group()) if m else None


def extract_mileage(text: str) -> int | None:
    if not text:
        return None
    text = str(text).replace(",", "")
    m = re.search(r"([\d]+)\s*(?:mi|miles)?", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if val < 1_000 and "k" in text.lower():
            val *= 1_000
        return val if val < 500_000 else None
    return None


def extract_price(text: str) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


# ── Browser factory ───────────────────────────────────────────────────────────

async def make_browser(playwright):
    """Launch a stealth-ish headless Chromium instance."""
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
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
    )
    # Hide webdriver flag from fingerprinting
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


# ══════════════════════════════════════════════════════════════════════════════
#  CRAIGSLIST
#  Strategy: Intercept JSON responses from the search endpoint first;
#  fall back to DOM parsing of server-rendered HTML if no JSON is captured.
# ══════════════════════════════════════════════════════════════════════════════

CL_SUBDOMAINS = {
    "San Francisco Bay Area": ["sfbay", "stockton", "modesto", "santacruz"],
    "Medford, OR":            ["medford", "eugene", "bend", "roseburg"],
}


async def search_craigslist(context, make: str, model: str, years: list, region: dict) -> list:
    listings = []
    sites = CL_SUBDOMAINS.get(region["name"], ["sfbay"])
    min_year, max_year = min(years), max(years)

    for site in sites:
        params = urlencode({
            "query":           f"{make} {model}",
            "min_auto_year":   min_year,
            "max_auto_year":   max_year,
            "auto_drivetrain": 4,   # AWD/4WD code
            "private_only":    1,
            "s":               0,
        })
        url = f"https://{site}.craigslist.org/search/cto?{params}"
        intercepted: list[dict] = []

        page: Page = await context.new_page()
        try:
            async def handle_response(response):
                if "search" in response.url and response.status == 200:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        try:
                            data = await response.json()
                            intercepted.append(data)
                        except Exception:
                            pass

            page.on("response", handle_response)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2_000)

            # Primary: intercepted JSON
            for data in intercepted:
                items = data.get("data", {}).get("items", data.get("items", []))
                for item in items:
                    title = item.get("Title") or item.get("title") or ""
                    price = extract_price(item.get("Ask") or item.get("price") or "")
                    href  = item.get("PostingURL") or item.get("url") or ""
                    listings.append(_cl_listing(title, price, href, make, model, region))

            # Fallback: DOM
            if not intercepted:
                cards = await page.query_selector_all("li.cl-static-search-result")
                for card in cards:
                    title_el = await card.query_selector(".title")
                    price_el = await card.query_selector(".price")
                    link_el  = await card.query_selector("a")
                    if not title_el:
                        continue
                    title      = (await title_el.inner_text()).strip()
                    price_text = (await price_el.inner_text()).strip() if price_el else ""
                    href       = await link_el.get_attribute("href") if link_el else ""
                    listings.append(_cl_listing(title, extract_price(price_text), href, make, model, region))

            log.info(f"  Craigslist [{site}]: {len(listings)} raw listings")

        except Exception as e:
            log.warning(f"  Craigslist [{site}] error: {e}")
        finally:
            await page.close()

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
#  Strategy: Intercept XHR calls to AutoTrader's listing API (/rest/lsc/
#  listings or similar). These return rich JSON with mileage, color, year,
#  price, and direct listing URLs — no HTML parsing needed.
#  Falls back to data-* attribute DOM parsing if interception yields nothing.
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
                        intercepted_listings.extend(items)
                        log.info(f"  AutoTrader intercepted {len(items)} listings from API")
                    except Exception:
                        pass

        page.on("response", handle_response)
        await page.goto(url, wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(3_000)

        # Primary: intercepted JSON
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

        # Fallback: DOM with stable data-* attributes
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
#  Strategy: Three-tier approach:
#    1. Intercept XHR JSON from the shopping API
#    2. Extract schema.org JSON-LD embedded in <script> tags (very stable)
#    3. Final fallback to DOM
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
        await page.goto(url, wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(3_000)

        # Tier 1: intercepted JSON
        for item in intercepted_listings:
            price   = extract_price(str(item.get("list_price") or item.get("price") or ""))
            mileage = item.get("mileage") or extract_mileage(str(item.get("miles", "")))
            year    = item.get("year") or extract_year(item.get("name", ""))
            color   = item.get("exterior_color") or item.get("color") or ""
            title   = item.get("name") or item.get("title") or f"{year} {make} {model}"
            slug    = item.get("url_slug") or item.get("url") or ""
            href    = f"https://www.cars.com{slug}" if slug.startswith("/") else slug
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

        # Tier 2: JSON-LD schema.org (extremely stable — rarely changes)
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

        # Tier 3: DOM fallback
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

def build_email_html(results_by_region: dict) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    rows_html = ""

    for region_name, listings in results_by_region.items():
        rows_html += f"""
        <tr>
          <td colspan="7" style="background:#1a1a2e;color:#e2e8f0;padding:12px 18px;
              font-size:14px;font-weight:700;letter-spacing:0.06em;
              border-top:2px solid #3b4fd8;">
            📍 {region_name}
          </td>
        </tr>"""

        if not listings:
            rows_html += """
        <tr>
          <td colspan="7" style="padding:14px 18px;color:#64748b;font-style:italic;">
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
                mileage_str = f"{l['mileage']:,}" if l.get("mileage") else "—"
                price_str   = f"${l['price']:,}" if l.get("price") else "—"
                color_str   = l.get("color") or "—"
                row_bg      = "#0f172a" if i % 2 == 0 else "#1e293b"
                rows_html += f"""
        <tr style="background:{row_bg};">
          <td style="padding:10px 14px;font-weight:700;color:#94a3b8;
                     font-size:13px;text-align:center;">{i}</td>
          <td style="padding:10px 14px;">
            <a href="{l['url']}" style="color:#60a5fa;text-decoration:none;
               font-weight:600;font-size:13px;">{l['title'][:65]}</a><br>
            <span style="font-size:11px;color:#475569;">{l['source']}</span>
          </td>
          <td style="padding:10px 14px;color:#f1f5f9;font-weight:600;">{price_str}</td>
          <td style="padding:10px 14px;color:#cbd5e1;">{mileage_str} mi</td>
          <td style="padding:10px 14px;color:#94a3b8;font-size:12px;">{color_str}</td>
          <td style="padding:10px 14px;text-align:center;">
            <span style="background:{score_color}20;color:{score_color};
                padding:3px 9px;border-radius:20px;font-size:12px;
                font-weight:800;letter-spacing:0.03em;">{score_pct}</span>
          </td>
          <td style="padding:10px 14px;color:#475569;font-size:11px;">{l.get('posted','')}</td>
        </tr>"""

    col_headers = ["#", "Listing", "Price", "Miles", "Color", "Score", "Posted"]
    col_html = "".join(
        f'<td style="padding:9px 14px;color:#334155;font-size:10px;'
        f'text-transform:uppercase;letter-spacing:0.1em;font-weight:700;">{h}</td>'
        for h in col_headers
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#080f1a;font-family:'Segoe UI',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:32px 16px;">
  <table width="860" cellpadding="0" cellspacing="0"
         style="border-radius:14px;overflow:hidden;border:1px solid #1e293b;
                box-shadow:0 20px 60px rgba(0,0,0,0.6);">

    <tr>
      <td colspan="7"
          style="background:linear-gradient(135deg,#0f2744 0%,#1a1a2e 100%);
                 padding:28px 24px;border-bottom:1px solid #1e3a5f;">
        <div style="font-size:24px;font-weight:900;color:#f1f5f9;
                    letter-spacing:-0.03em;">🚗 Daily Car Deal Digest</div>
        <div style="font-size:12px;color:#475569;margin-top:6px;letter-spacing:0.04em;">
          {today} &nbsp;·&nbsp; Honda CR-V &amp; Mazda CX-5
          &nbsp;·&nbsp; AWD &nbsp;·&nbsp; Private Party &nbsp;·&nbsp; &lt;70,000 mi
        </div>
      </td>
    </tr>

    <tr style="background:#0b1526;border-bottom:1px solid #1e293b;">
      {col_html}
    </tr>

    {rows_html}

    <tr>
      <td colspan="7"
          style="background:#080f1a;padding:14px 24px;
                 color:#1e293b;font-size:11px;border-top:1px solid #0f172a;">
        Score: year 40% · mileage 40% · price 20% &nbsp;|&nbsp;
        Green ≥65 · Yellow ≥40 · Red &lt;40 &nbsp;|&nbsp;
        New listings only · Powered by Playwright
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
    new_seen: set = set()
    results_by_region: dict = {}

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
                    raw += await search_craigslist(context, make, model, years, region)
                    raw += await search_autotrader(context, make, model, years, region)
                    raw += await search_cars_dot_com(context, make, model, years, region)

                    for listing in raw:
                        lid = listing_id(listing)
                        if lid in seen or lid in new_seen:
                            continue
                        if not listing.get("url"):
                            continue
                        if not passes_filters(listing, config):
                            continue
                        listing["score"] = value_score(listing, config)
                        region_listings.append(listing)
                        new_seen.add(lid)

                region_listings.sort(key=lambda x: x["score"], reverse=True)
                results_by_region[region["name"]] = region_listings[:25]
                log.info(f"\n✓ {region['name']}: {len(region_listings)} qualifying new listings")

        finally:
            await context.close()
            await browser.close()

    save_seen(seen | new_seen)

    total   = sum(len(v) for v in results_by_region.values())
    subject = f"🚗 Car Deal Digest — {total} new listings · {date.today().strftime('%b %d')}"
    html    = build_email_html(results_by_region)
    send_email(subject, html)
    log.info(f"\nDone. {total} new listings delivered.")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
