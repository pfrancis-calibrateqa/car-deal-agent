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
import argparse
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlencode, quote_plus
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from contextlib import contextmanager
import time

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

# ── Progress Manager ──────────────────────────────────────────────────────────

class ProgressManager:
    """Manages progress display for all scraping operations using rich library."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.console = Console()
        self.progress = None
        self.stats = {
            "listings_found": 0,
            "api_calls": 0,
            "filtered_count": 0,
            "start_time": None
        }
        
        if self.enabled:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
                transient=False  # Keep progress visible
            )
    
    @contextmanager
    def task(self, description: str):
        """Context manager for a single task with spinner."""
        if not self.enabled or self.progress is None:
            # If disabled, just log the message
            log.info(description)
            yield None
            return
        
        task_id = self.progress.add_task(description, total=None)
        try:
            yield task_id
        except Exception as e:
            self.progress.update(task_id, description=f"✗ {description}: {e}")
            raise
    
    def update_task(self, task_id, description: str):
        """Update task description."""
        if self.enabled and task_id is not None and self.progress is not None:
            self.progress.update(task_id, description=description)
            # Also log for permanent record
            log.info(description)
    
    def start(self):
        """Start progress display and timer."""
        self.stats["start_time"] = time.time()
        if self.enabled and self.progress is not None:
            self.progress.start()
    
    def stop(self):
        """Stop progress display."""
        if self.enabled and self.progress is not None:
            self.progress.stop()
    
    def print_summary(self):
        """Print final execution summary."""
        if not self.enabled:
            return
        
        elapsed = time.time() - self.stats["start_time"] if self.stats["start_time"] else 0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        self.console.print("\n📊 Summary:", style="bold cyan")
        self.console.print(f"  • Found: {self.stats['listings_found']} listings", style="cyan")
        self.console.print(f"  • After filtering: {self.stats['filtered_count']} listings", style="cyan")
        self.console.print(f"  • API calls: {self.stats['api_calls']}", style="cyan")
        self.console.print(f"  • Execution time: {minutes}m {seconds}s", style="cyan")

# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)
# ── Error Handling ────────────────────────────────────────────────────────────

@dataclass
class ScrapingError:
    """Represents a scraping error."""
    source: str
    error_type: str
    message: str
    timestamp: datetime


class ErrorHandler:
    """Manages error tracking and reporting for scraping operations."""

    def __init__(self):
        self.errors: List[ScrapingError] = []
        self.last_successful_run: Optional[datetime] = None
        self.last_run_file = ROOT / "data" / "last_successful_run.txt"
        self.load_last_run()

    def record_error(self, source: str, error: Exception):
        """Record a scraping error."""
        self.errors.append(ScrapingError(
            source=source,
            error_type=type(error).__name__,
            message=str(error),
            timestamp=datetime.now()
        ))
        log.error(f"Error recorded for {source}: {type(error).__name__} - {error}")

    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0

    def build_error_section(self) -> str:
        """Build HTML error section for email."""
        if not self.errors:
            return ""

        html = """
        <tr>
          <td colspan="8" style="background:linear-gradient(135deg,#78350f 0%,#92400e 100%);padding:16px 24px;border-bottom:2px solid #f59e0b;">
            <div style="font-size:14px;color:#fbbf24;font-weight:600;margin-bottom:8px;">
              ⚠️ SCRAPING ISSUES
            </div>
            <div style="font-size:13px;color:#fde68a;line-height:1.6;">
              Some sources encountered errors:
            </div>
        """

        for error in self.errors:
            html += f"""
            <div style="margin-top:12px;padding:12px;background:#451a03;border-radius:4px;">
              <div style="font-weight:600;color:#fbbf24;">❌ {error.source}</div>
              <div style="font-size:12px;color:#fde68a;margin-top:4px;">
                Error: {error.error_type} - {error.message[:200]}
              </div>
              <div style="font-size:11px;color:#a16207;margin-top:4px;">
                Time: {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
              </div>
            </div>
            """

        html += """
            <div style="margin-top:16px;font-size:12px;color:#fde68a;">
              🔧 Troubleshooting:<br>
              • Try running manually: <code style="background:#451a03;padding:2px 6px;border-radius:3px;">python src/search_agent.py</code><br>
              • Check internet connection and site availability<br>
              • Review logs for detailed error information
            </div>
          </td>
        </tr>
        """
        return html

    def get_email_subject(self, listing_count: int, good_deal_count: int) -> str:
        """Generate email subject line with status."""
        if not self.errors and listing_count > 0:
            if good_deal_count > 0:
                return f"🚗 Daily Car Deal Digest: {listing_count} listings, {good_deal_count} great deals"
            else:
                return f"🚗 Daily Car Deal Digest: {listing_count} listings"
        elif self.errors and listing_count > 0:
            return f"🚗 Daily Car Deal Digest: {listing_count} listings (⚠️ some sources failed)"
        elif not self.errors and listing_count == 0:
            return "🚗 Daily Car Deal Digest: No new listings today"
        else:
            return "🚗 Daily Car Deal Digest: ⚠️ Scraping failed"

    def save_last_run(self):
        """Save timestamp of successful run."""
        self.last_run_file.parent.mkdir(exist_ok=True)
        with open(self.last_run_file, "w") as f:
            f.write(datetime.now().isoformat())
        log.info("Saved last successful run timestamp")

    def load_last_run(self):
        """Load timestamp of last successful run."""
        try:
            if self.last_run_file.exists():
                with open(self.last_run_file) as f:
                    self.last_successful_run = datetime.fromisoformat(f.read().strip())
                log.info(f"Last successful run: {self.last_successful_run}")
        except Exception as e:
            log.warning(f"Could not load last run timestamp: {e}")
            self.last_successful_run = None



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


def days_on_market(posted_date_str: str) -> str:
    """
    Calculate how many days a listing has been on the market.
    Returns a human-readable string like "2d" or "15d" or "Today".
    """
    if not posted_date_str:
        return "—"
    
    try:
        posted = datetime.fromisoformat(posted_date_str).date()
        today = date.today()
        days = (today - posted).days
        
        if days == 0:
            return "Today"
        elif days == 1:
            return "1d"
        else:
            return f"{days}d"
    except Exception:
        return "—"


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

    # STRICT: Only allow vehicles that match configured make/model combinations
    valid_vehicles = {
        (s["make"].lower(), s["model"].lower())
        for s in config["searches"]
    }
    listing_make = (listing.get("make") or "").lower()
    listing_model = (listing.get("model") or "").lower()
    
    if (listing_make, listing_model) not in valid_vehicles:
        log.info(f"  ⚠️  Filtered out (wrong vehicle): {listing_make} {listing_model} - not in search criteria")
        return False

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

    # Get ZIP code for regional pricing
    region_name = listing.get("region")
    zip_code = None
    if region_name:
        # Load config to get ZIP code for this region
        config = load_config()
        for region in config.get("regions", []):
            if region["name"] == region_name:
                zip_code = region["center_zip"]
                break

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
        region       = region_name,                  # For regional pricing
        zip_code     = zip_code,                     # For MarketCheck API
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


def is_suspicious_price(price: int) -> bool:
    """
    Check if a price looks like a placeholder/fake price.
    Prices below $2000 are suspicious for vehicles and often indicate:
    - Placeholder prices ($1, $100, $500, $1000)
    - Sequential patterns ($123, $1234)
    - Down payment amounts instead of full price
    """
    if price is None:
        return False
    return price < 2000


def extract_real_price_from_text(text: str, year: int = None) -> int:
    """
    Extract the real vehicle price from listing description text.
    Looks for common price patterns like "$15,000" or "15000" or "asking 15k"
    
    Returns the most likely real price, or None if not found.
    """
    if not text:
        return None
    
    # Pattern 1: $XX,XXX or $XX XXX format
    pattern1 = r'\$\s*(\d{1,3}[,\s]\d{3}(?:[,\s]\d{3})*)'
    matches1 = re.findall(pattern1, text)
    
    # Pattern 2: Plain numbers that look like prices (4-5 digits)
    pattern2 = r'\b(\d{4,5})\b'
    matches2 = re.findall(pattern2, text)
    
    # Pattern 3: "asking X" or "price X" or "X obo"
    pattern3 = r'(?:asking|price|asking price|obo|firm)\s*:?\s*\$?\s*(\d{1,3}[,\s]?\d{3}(?:[,\s]\d{3})*)'
    matches3 = re.findall(pattern3, text.lower())
    
    # Combine all matches and clean them
    all_matches = matches1 + matches2 + matches3
    prices = []
    
    for match in all_matches:
        # Remove commas and spaces
        clean = re.sub(r'[,\s]', '', match)
        try:
            price = int(clean)
            # Filter reasonable car prices ($3,000 - $100,000)
            if 3000 <= price <= 100000:
                prices.append(price)
        except ValueError:
            continue
    
    if not prices:
        return None
    
    # If we have a year, prefer prices that make sense for that year
    if year and prices:
        # Rough heuristic: newer cars should be more expensive
        if year >= 2020:
            # Prefer prices > $15k for newer cars
            expensive = [p for p in prices if p >= 15000]
            if expensive:
                return max(expensive)  # Return highest reasonable price
        elif year >= 2015:
            # Prefer prices > $10k for mid-age cars
            mid_range = [p for p in prices if 10000 <= p <= 50000]
            if mid_range:
                return max(mid_range)
    
    # Return the highest price found (most likely the asking price)
    # Lower numbers might be down payment, monthly payment, etc.
    return max(prices)


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

# ── Deep Inspection ───────────────────────────────────────────────────────────

def extract_trim_from_title(title: str, make: str, model: str, description: str = None) -> tuple:
    """
    Extract trim level from listing title or description.
    Common Honda CR-V trims: LX, EX, EX-L, EXL, Touring, Sport
    Common Mazda CX-5 trims: Sport, Touring, Grand Touring, Carbon, Signature
    
    Returns: (trim_name, found_in_description)
    - trim_name: The extracted trim level or None
    - found_in_description: True if found in description, False if in title
    """
    if not title:
        return None, False
    
    # Common trim patterns
    trim_patterns = {
        # Honda CR-V
        "TOURING": "Touring",
        "EX-L": "EX-L",
        "EXL": "EX-L",
        "EX ": "EX",
        " EX": "EX",
        "LX": "LX",
        "SPORT": "Sport",
        
        # Mazda CX-5
        "SIGNATURE": "Signature",
        "GRAND TOURING": "Grand Touring",
        "CARBON": "Carbon",
        # "TOURING": "Touring",  # Already covered above
        # "SPORT": "Sport",      # Already covered above
    }
    
    # First, try to find trim in title
    title_clean = title.upper()
    if make:
        title_clean = title_clean.replace(make.upper(), "")
    if model:
        title_clean = title_clean.replace(model.upper().replace("-", " "), "")
        title_clean = title_clean.replace(model.upper().replace("-", ""), "")
    
    for pattern, trim_name in trim_patterns.items():
        if pattern in title_clean:
            return trim_name, False
    
    # If not found in title and description provided, search description
    if description:
        description_clean = description.upper()
        for pattern, trim_name in trim_patterns.items():
            if pattern in description_clean:
                return trim_name, True
    
    return None, False


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
        
        # Extract full title for trim parsing
        title_el = await page.query_selector('#titletextonly')
        full_title = (await title_el.inner_text()).strip() if title_el else listing.get("title", "")
        
        # Extract full description
        body_el = await page.query_selector('#postingbody')
        description = (await body_el.inner_text()).strip() if body_el else ""
        
        # Extract trim from title first, then description if not found
        trim, found_in_desc = extract_trim_from_title(full_title, listing.get("make"), listing.get("model"), description)
        
        # Extract posting date (Craigslist specific)
        posted_date = None
        try:
            # Craigslist shows posting date in <time> tag or .postinginfo
            time_el = await page.query_selector('time')
            if time_el:
                datetime_attr = await time_el.get_attribute('datetime')
                if datetime_attr:
                    # Parse ISO format date (e.g., "2026-03-05T10:30:00-0800")
                    posted_date = datetime_attr.split('T')[0]  # Get just the date part
            
            # Fallback: look for "posted: " text
            if not posted_date:
                postinginfo_els = await page.query_selector_all('.postinginfo')
                for el in postinginfo_els:
                    text = await el.inner_text()
                    if 'posted:' in text.lower():
                        # Extract date from text like "posted: 2026-03-05"
                        import re
                        match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                        if match:
                            posted_date = match.group(1)
                            break
        except Exception:
            pass  # If date extraction fails, keep the default
        
        if posted_date:
            listing["posted"] = posted_date
        
        # Check for suspicious price and try to extract real price
        current_price = listing.get("price")
        if current_price and is_suspicious_price(current_price):
            log.info(f"  🔍 Suspicious price ${current_price} detected, searching for real price...")
            
            # Try to extract real price from description
            real_price = extract_real_price_from_text(description, listing.get("year"))
            
            if real_price:
                log.info(f"     ✓ Found real price: ${real_price:,} (was ${current_price})")
                listing["price"] = real_price
                listing["price_source"] = "extracted_from_description"
            else:
                log.info(f"     ✗ Could not find real price, filtering out listing")
                return None  # Filter out if we can't find real price
        
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
        if trim:
            listing["trim"] = trim  # This will be used by DealScorer
            listing["trim_from_description"] = found_in_desc  # Track if we should append to title
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
    # Extract actual make/model from title to validate against search params
    title_lower = title.lower()
    
    # Check if the title actually contains the make and model we're searching for
    # This prevents Craigslist from returning wrong vehicles
    if make.lower() not in title_lower or model.lower().replace("-", " ") not in title_lower.replace("-", " "):
        # Title doesn't match - extract what's actually there
        # Common makes to check
        actual_make = None
        actual_model = None
        
        for check_make in ["honda", "mazda", "toyota", "ford", "chevy", "buick", "gmc", "nissan"]:
            if check_make in title_lower:
                actual_make = check_make.title()
                break
        
        # If we found a different make, use it (this will be filtered out later)
        if actual_make and actual_make.lower() != make.lower():
            make = actual_make
            # Try to extract model from title
            model = "Unknown"
    
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

def format_title_with_trim(listing: dict, max_length: int = 60) -> str:
    """
    Format listing title, appending trim in parentheses if it was found in description.
    
    Examples:
    - "2021 Mazda CX-5" + trim "Signature" from description -> "2021 Mazda CX-5 (Signature)"
    - "2020 Honda CR-V Touring" (trim already in title) -> "2020 Honda CR-V Touring"
    """
    title = listing.get("title", "")
    trim = listing.get("trim")
    trim_from_desc = listing.get("trim_from_description", False)
    
    # Only append trim if it was found in description (not already in title)
    if trim and trim_from_desc:
        formatted = f"{title} ({trim})"
    else:
        formatted = title
    
    # Truncate to max length
    return formatted[:max_length]


def _deal_cell(listing: dict) -> tuple[str, str]:
    """
    Returns (cell_html, sort_key) for the Deal column.

    Layout inside the cell:
      Line 1 — grade emoji + label          e.g. "🔥 Steal"
      Line 2 — % vs market + region tag     e.g. "18.4% below  [SF]"
      Line 3 — savings dollar amount        e.g. "save $4,200"
      
    Red flag (🚩) added for deals ≥45% below market (too good to be true).

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
            '<span style="color:#cbd5e1;font-size:12px;">— no data</span>',
            -999
        )

    # Check for "too good to be true" deals (≥40% below market)
    red_flag = ""
    if pct >= 40:
        red_flag = '<span style="font-size:14px;margin-left:4px;" title="Too good to be true? Verify carefully">🚩</span>'

    # Colour the percentage line: green = good deal, amber = fair, red = over
    if pct >= 10:
        pct_color = "#4ade80"  # Lighter green for better contrast
    elif pct >= 0:
        pct_color = "#fbbf24"  # Lighter amber for better contrast
    else:
        pct_color = "#ef4444"

    direction  = "below" if pct >= 0 else "above"
    pct_str    = f"{abs(pct):.1f}% {direction}"

    # Savings line
    if vs_avg is not None:
        if vs_avg < 0:
            savings_str = f"save ${abs(vs_avg):,}"
            savings_color = "#4ade80"  # Lighter green for better contrast
        else:
            savings_str = f"${vs_avg:,} over"
            savings_color = "#ef4444"
    else:
        savings_str   = ""
        savings_color = "#94a3b8"

    mkt_str = f"mkt avg ${mkt_avg:,}" if mkt_avg else ""

    cell_html = f"""
        <span style="font-size:12px;font-weight:700;color:#f1f5f9;">{grade}{red_flag}</span><br>
        <span style="font-size:11px;color:{pct_color};">{pct_str}</span>
        <span style="font-size:10px;color:#cbd5e1;margin-left:4px;">[{region_tag}]</span><br>
        <span style="font-size:11px;color:{savings_color};">{savings_str}</span>
        <span style="font-size:10px;color:#94a3b8;margin-left:4px;">{mkt_str}</span>
    """
    return cell_html, pct   # sort key = pct_below_market


def build_email_html(results_by_region: dict, error_handler: ErrorHandler = None) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    
    # Find the best deal across all regions (highest % below market with good grade)
    all_listings = []
    for region_name, listings in results_by_region.items():
        all_listings.extend(listings)
    
    # Filter for actual good deals (at least "Good Deal" grade)
    # EXCLUDE red-flagged listings (≥40% below) from top pick consideration
    good_deals = [
        l for l in all_listings 
        if l.get("deal_pct") and 5 <= l.get("deal_pct") < 40  # Between 5% and 40% below market
    ]
    
    # Sort by deal_pct (highest % below market first)
    top_pick = None
    if good_deals:
        good_deals.sort(key=lambda x: x.get("deal_pct", 0), reverse=True)
        top_pick = good_deals[0]
    
    # Find red-flagged listings (≥40% below market - too good to be true)
    red_flagged = [
        l for l in all_listings
        if l.get("deal_pct") and l.get("deal_pct") >= 40
    ]
    # Sort red-flagged by % below market (highest first)
    red_flagged.sort(key=lambda x: x.get("deal_pct", 0), reverse=True)
    
    # Build top pick section HTML
    top_pick_html = ""
    if top_pick:
        region_tag = REGION_TAGS.get(top_pick.get("region", ""), "")
        mileage_str = f"{top_pick['mileage']:,}" if top_pick.get("mileage") else "—"
        price_str = f"${top_pick['price']:,}" if top_pick.get("price") else "—"
        savings = abs(top_pick.get("deal_vs_avg", 0))
        pct = top_pick.get("deal_pct", 0)
        
        top_pick_html = f"""
    <tr>
      <td colspan="8" style="background:linear-gradient(135deg,#1e3a8a 0%,#3b4fd8 100%);
                             padding:20px 24px;border-bottom:2px solid #60a5fa;">
        <div class="top-pick-container" style="display:flex;align-items:center;justify-content:space-between;">
          <div class="top-pick-content" style="flex:1;">
            <div style="font-size:14px;color:#93c5fd;font-weight:600;
                       letter-spacing:0.05em;margin-bottom:8px;">
              🔥 TOP PICK TODAY
            </div>
            <div style="font-size:20px;font-weight:800;color:#f1f5f9;
                       margin-bottom:6px;line-height:1.3;">
              {format_title_with_trim(top_pick, 70)}
            </div>
            <div style="font-size:13px;color:#cbd5e1;margin-bottom:12px;">
              {top_pick['source']} · {top_pick.get('region', '')} [{region_tag}]
            </div>
            <div class="top-pick-metrics" style="display:flex;gap:35px;flex-wrap:wrap;">
              <div style="margin-bottom:12px;min-width:100px;">
                <div style="font-size:11px;color:#cbd5e1;text-transform:uppercase;
                           letter-spacing:0.05em;">Price</div>
                <div style="font-size:18px;font-weight:700;color:#f1f5f9;">
                  {price_str}
                </div>
              </div>
              <div style="margin-bottom:12px;min-width:100px;">
                <div style="font-size:11px;color:#cbd5e1;text-transform:uppercase;
                           letter-spacing:0.05em;">Mileage</div>
                <div style="font-size:18px;font-weight:700;color:#f1f5f9;">
                  {mileage_str} mi
                </div>
              </div>
              <div style="margin-bottom:12px;min-width:100px;">
                <div style="font-size:11px;color:#cbd5e1;text-transform:uppercase;
                           letter-spacing:0.05em;">Deal Grade</div>
                <div style="font-size:18px;font-weight:700;color:#4ade80;">
                  {top_pick.get('deal_grade', 'N/A')}
                </div>
              </div>
              <div style="margin-bottom:12px;min-width:100px;">
                <div style="font-size:11px;color:#cbd5e1;text-transform:uppercase;
                           letter-spacing:0.05em;">You Save</div>
                <div style="font-size:18px;font-weight:700;color:#4ade80;">
                  ${savings:,}
                </div>
              </div>
              <div style="margin-bottom:12px;min-width:100px;">
                <div style="font-size:11px;color:#cbd5e1;text-transform:uppercase;
                           letter-spacing:0.05em;">vs Market</div>
                <div style="font-size:18px;font-weight:700;color:#4ade80;">
                  {pct:.1f}% below
                </div>
              </div>
            </div>
          </div>
          <div class="top-pick-cta" style="margin-left:20px;">
            <a href="{top_pick['url']}" 
               style="display:inline-block;background:#4ade80;color:#0f172a;
                      padding:14px 28px;border-radius:8px;text-decoration:none;
                      font-weight:700;font-size:14px;letter-spacing:0.02em;
                      box-shadow:0 4px 12px rgba(34,197,94,0.3);">
              VIEW LISTING →
            </a>
          </div>
        </div>
      </td>
    </tr>"""
    
    # Build red flag section HTML (for suspiciously low prices)
    red_flag_html = ""
    if red_flagged:
        red_flag_html = f"""
    <tr>
      <td colspan="8" style="background:linear-gradient(135deg,#7f1d1d 0%,#991b1b 100%);
                             padding:16px 24px;border-bottom:2px solid #dc2626;">
        <div style="font-size:14px;color:#fca5a5;font-weight:600;
                   letter-spacing:0.05em;margin-bottom:4px;">
          🚩 VERIFY THESE DEALS CAREFULLY
        </div>
        <div style="font-size:11px;color:#fecaca;line-height:1.5;">
          These listings are ≥40% below market price. While they may be legitimate, 
          verify carefully for salvage titles, scams, or data errors.
        </div>
      </td>
    </tr>"""
        
        # Add table headers for red flag section
        col_headers = ["#", "Listing", "Price", "Miles", "Color", "Deal vs Market", "Score", "Posted"]
        col_html = "".join(
            f'<td style="padding:9px 12px;color:#64748b;font-size:10px;'
            f'text-transform:uppercase;letter-spacing:0.1em;font-weight:700;">{h}</td>'
            for h in col_headers
        )
        red_flag_html += f"""
    <tr style="background:#0b1526;border-bottom:1px solid #1e293b;">
      {col_html}
    </tr>"""
        
        # Add red-flagged listings
        for i, l in enumerate(red_flagged, 1):
            score_pct   = int(l["score"] * 100)
            score_color = (
                "#22c55e" if score_pct >= 65
                else "#f59e0b" if score_pct >= 40
                else "#ef4444"
            )
            mileage_str  = f"{l['mileage']:,}" if l.get("mileage") else "—"
            price_str    = f"${l['price']:,}" if l.get("price") else "—"
            color_str    = l.get("color") or "—"
            row_bg       = "#1a0b0b" if i % 2 == 0 else "#2d1111"  # Darker red tint
            deal_html, _ = _deal_cell(l)

            red_flag_html += f"""
        <tr style="background:{row_bg};">
          <td style="padding:10px 10px;font-weight:700;color:#cbd5e1;
                     font-size:13px;text-align:center;width:32px;">{i}</td>
          <td style="padding:10px 12px;min-width:200px;">
            <a href="{l['url']}" style="color:#60a5fa;text-decoration:none;
               font-weight:600;font-size:13px;">{format_title_with_trim(l, 60)}</a><br>
            <span style="font-size:11px;color:#cbd5e1;">{l['source']} · {l.get('region', '')}</span>
          </td>
          <td style="padding:10px 10px;color:#f1f5f9;font-weight:600;
                     white-space:nowrap;">{price_str}</td>
          <td style="padding:10px 10px;color:#cbd5e1;white-space:nowrap;">{mileage_str} mi</td>
          <td style="padding:10px 10px;color:#cbd5e1;font-size:12px;">{color_str}</td>
          <td style="padding:10px 12px;min-width:160px;">{deal_html}</td>
          <td style="padding:10px 10px;text-align:center;white-space:nowrap;">
            <span style="background:{score_color}20;color:{score_color};
                padding:3px 9px;border-radius:20px;font-size:12px;
                font-weight:800;letter-spacing:0.03em;">{score_pct}</span>
          </td>
          <td style="padding:10px 10px;color:#cbd5e1;font-size:12px;
                     white-space:nowrap;">{days_on_market(l.get('posted',''))}</td>
        </tr>"""
    
    rows_html = ""
    
    # Add troubleshooting tips if no listings found
    no_listings_found = all(len(listings) == 0 for listings in results_by_region.values())
    troubleshooting_html = ""
    
    if no_listings_found:
        troubleshooting_html = """
        <tr>
          <td colspan="8" style="background:#1a1a2e;padding:20px 24px;border-top:2px solid #3b4fd8;">
            <div style="font-size:14px;color:#fbbf24;font-weight:600;margin-bottom:12px;">
              💡 No New Listings Found
            </div>
            <div style="font-size:13px;color:#cbd5e1;line-height:1.6;">
              This could mean:<br>
              • All current listings have already been sent to you<br>
              • No new listings match your search criteria today<br>
              • Listings may have been filtered out (salvage titles, manual transmission, etc.)<br>
              <br>
              <strong style="color:#f1f5f9;">What you can do:</strong><br>
              • Check back tomorrow for new listings<br>
              • Review your search criteria in <code style="background:#0f172a;padding:2px 6px;border-radius:3px;">config/search_criteria.json</code><br>
              • Expand your search years or mileage limits<br>
              • Consider additional makes/models
            </div>
          </td>
        </tr>"""

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
          <td colspan="8" style="padding:14px 18px;color:#cbd5e1;font-style:italic;">
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
          <td style="padding:10px 10px;font-weight:700;color:#cbd5e1;
                     font-size:13px;text-align:center;width:32px;">{i}</td>
          <td style="padding:10px 12px;min-width:200px;">
            <a href="{l['url']}" style="color:#60a5fa;text-decoration:none;
               font-weight:600;font-size:13px;">{format_title_with_trim(l, 60)}</a><br>
            <span style="font-size:11px;color:#cbd5e1;">{l['source']}</span>
          </td>
          <td style="padding:10px 10px;color:#f1f5f9;font-weight:600;
                     white-space:nowrap;">{price_str}</td>
          <td style="padding:10px 10px;color:#cbd5e1;white-space:nowrap;">{mileage_str} mi</td>
          <td style="padding:10px 10px;color:#cbd5e1;font-size:12px;">{color_str}</td>
          <td style="padding:10px 12px;min-width:160px;">{deal_html}</td>
          <td style="padding:10px 10px;text-align:center;white-space:nowrap;">
            <span style="background:{score_color}20;color:{score_color};
                padding:3px 9px;border-radius:20px;font-size:12px;
                font-weight:800;letter-spacing:0.03em;">{score_pct}</span>
          </td>
          <td style="padding:10px 10px;color:#cbd5e1;font-size:12px;
                     white-space:nowrap;">{days_on_market(l.get('posted',''))}</td>
        </tr>"""

    # 8 columns now (added Deal)
    col_headers = ["#", "Listing", "Price", "Miles", "Color", "Deal vs Market", "Score", "Age"]
    col_html = "".join(
        f'<td style="padding:9px 12px;color:#cbd5e1;font-size:11px;'
        f'text-transform:uppercase;letter-spacing:0.1em;font-weight:700;">{h}</td>'
        for h in col_headers
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=yes">
<style>
  /* Base styles */
  body {{
    -webkit-text-size-adjust: 100%;
    -ms-text-size-adjust: 100%;
  }}
  
  /* Desktop: show table, hide cards */
  .desktop-table {{ display: table; }}
  .mobile-cards {{ display: none; }}
  
  /* Mobile styles */
  @media only screen and (max-width: 600px) {{
    /* Hide desktop table, show mobile cards */
    .desktop-table {{ display: none !important; }}
    .mobile-cards {{ display: block !important; }}
    
    /* Top Pick mobile optimization */
    .top-pick-container {{
      display: block !important;
    }}
    
    .top-pick-content {{
      margin-bottom: 16px !important;
    }}
    
    .top-pick-metrics {{
      display: grid !important;
      grid-template-columns: 1fr 1fr !important;
      gap: 12px !important;
    }}
    
    .top-pick-cta {{
      margin-left: 0 !important;
      width: 100% !important;
    }}
    
    .top-pick-cta a {{
      display: block !important;
      width: 100% !important;
      text-align: center !important;
      box-sizing: border-box !important;
    }}
    
    /* Red Flag section mobile optimization */
    .red-flag-warning {{
      font-size: 12px !important;
      line-height: 1.6 !important;
    }}
    
    /* Mobile card styles */
    .mobile-card {{
      background: #1e293b;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 12px;
      border: 1px solid #334155;
    }}
    
    .deal-badge {{
      display: inline-block;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    
    .listing-title {{
      font-size: 18px;
      font-weight: 700;
      color: #f1f5f9;
      margin: 0 0 12px 0;
      line-height: 1.3;
    }}
    
    .price {{
      font-size: 24px;
      font-weight: 800;
      color: #4ade80;
      margin-bottom: 8px;
    }}
    
    .metrics {{
      font-size: 14px;
      color: #cbd5e1;
      margin-bottom: 8px;
      line-height: 1.6;
    }}
    
    .metrics span {{
      display: inline-block;
      margin-right: 12px;
    }}
    
    .source {{
      font-size: 12px;
      color: #94a3b8;
      margin-bottom: 12px;
    }}
    
    .cta-button {{
      display: block;
      width: 100%;
      padding: 14px 20px;
      background: #4ade80;
      color: #0f172a;
      text-align: center;
      text-decoration: none;
      font-weight: 700;
      font-size: 16px;
      border-radius: 8px;
      min-height: 44px;
      box-sizing: border-box;
    }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#080f1a;font-family:'Segoe UI',system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:32px 16px;">
  <table class="desktop-table" width="100%" style="max-width:960px;border-radius:14px;overflow:hidden;border:1px solid #1e293b;
                box-shadow:0 20px 60px rgba(0,0,0,0.6);" cellpadding="0" cellspacing="0">

    <tr>
      <td colspan="8"
          style="background:linear-gradient(135deg,#0f2744 0%,#1a1a2e 100%);
                 padding:28px 24px;border-bottom:1px solid #1e3a5f;">
        <div style="font-size:24px;font-weight:900;color:#f1f5f9;
                    letter-spacing:-0.03em;">🚗 Daily Car Deal Digest</div>
        <div style="font-size:12px;color:#cbd5e1;margin-top:6px;letter-spacing:0.04em;">
          {today} &nbsp;·&nbsp; Honda CR-V &amp; Mazda CX-5
          &nbsp;·&nbsp; AWD &nbsp;·&nbsp; Private Party &nbsp;·&nbsp; &lt;70,000 mi
          &nbsp;·&nbsp; Deal scores vs national market avg
        </div>
      </td>
    </tr>

    {top_pick_html}

    {error_handler.build_error_section() if error_handler else ""}

    {red_flag_html}

    <tr>
      <td colspan="8" style="background:#1a1a2e;color:#e2e8f0;padding:12px 18px;
          font-size:14px;font-weight:700;letter-spacing:0.06em;
          border-top:2px solid #3b4fd8;">
        📋 ALL LISTINGS BY REGION
      </td>
    </tr>

    <tr style="background:#0b1526;border-bottom:1px solid #1e293b;">
      {col_html}
    </tr>

    {troubleshooting_html}

    {rows_html}

    <tr>
      <td colspan="8"
          style="background:#080f1a;padding:14px 24px;
                 color:#94a3b8;font-size:12px;border-top:1px solid #0f172a;line-height:1.6;">
        <div style="margin-bottom:12px;">
          Score: year 40% · mileage 40% · price 20%
          &nbsp;|&nbsp; Green ≥65 · Yellow ≥40 · Red &lt;40
          &nbsp;|&nbsp; Deal vs Market: MarketCheck national avg (mileage-adjusted)
          &nbsp;|&nbsp; [SF] = Bay Area listing · [MED] = Medford listing
          &nbsp;·&nbsp; SF prices typically run higher than national avg
          &nbsp;|&nbsp; New listings only · Powered by Playwright
        </div>
        <div style="padding-top:12px;border-top:1px solid #1e293b;font-size:11px;color:#64748b;">
          📊 Status: 
          {f"Last successful run: {error_handler.last_successful_run.strftime('%b %d, %Y at %I:%M %p')}" if error_handler and error_handler.last_successful_run else "First run"}
          &nbsp;·&nbsp; 
          Script version: 2.0
          &nbsp;·&nbsp;
          Generated: {datetime.now().strftime('%b %d, %Y at %I:%M %p')}
        </div>
      </td>
    </tr>

  </table>
  </td></tr>
  </table>
  
  {build_mobile_cards(results_by_region, top_pick, red_flagged)}
  
</body>
</html>"""
def build_mobile_card(listing: dict) -> str:
    """
    Build a single mobile card for a listing.
    Returns HTML string for one card with deal badge, title, price, metrics, source, and CTA.
    """
    # Format title with trim
    title = format_title_with_trim(listing, max_length=50)

    # Format price
    price_str = f"${listing['price']:,}" if listing.get('price') else "—"

    # Format mileage
    mileage_str = f"{listing['mileage']:,} mi" if listing.get('mileage') else "—"

    # Deal information
    deal_grade = listing.get('deal_grade', 'N/A')
    deal_pct = listing.get('deal_pct', 0)
    savings = abs(listing.get('deal_vs_avg', 0))

    # Format deal percentage
    if deal_pct > 0:
        deal_pct_str = f"{deal_pct:.1f}% below market"
        deal_pct_color = "#4ade80"  # green
    elif deal_pct < 0:
        deal_pct_str = f"{abs(deal_pct):.1f}% above market"
        deal_pct_color = "#ef4444"  # red
    else:
        deal_pct_str = "at market"
        deal_pct_color = "#fbbf24"  # yellow

    # Format savings
    if listing.get('deal_vs_avg'):
        if listing['deal_vs_avg'] < 0:
            savings_str = f"Save ${savings:,}"
            savings_color = "#4ade80"
        else:
            savings_str = f"${savings:,} over"
            savings_color = "#ef4444"
    else:
        savings_str = "—"
        savings_color = "#cbd5e1"

    # Source and region
    region_tag = REGION_TAGS.get(listing.get("region", ""), "")
    source_str = f"{listing['source']} • {listing.get('region', '')} [{region_tag}] • {days_on_market(listing.get('posted', ''))}"

    # Deal badge background color
    if deal_pct >= 40:
        badge_bg = "#7f1d1d"  # red for suspicious deals
        badge_text = "#fca5a5"
    elif deal_pct >= 15:
        badge_bg = "#1e3a8a"  # blue for great deals
        badge_text = "#93c5fd"
    elif deal_pct >= 5:
        badge_bg = "#065f46"  # green for good deals
        badge_text = "#6ee7b7"
    else:
        badge_bg = "#78350f"  # orange for fair/overpriced
        badge_text = "#fbbf24"

    return f"""
    <div class="mobile-card" style="background:#1e293b;border-radius:8px;padding:16px;margin-bottom:12px;border:1px solid #334155;">
      <div class="deal-badge" style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700;margin-bottom:8px;background:{badge_bg};color:{badge_text};">
        {deal_grade}
      </div>
      <h3 class="listing-title" style="font-size:18px;font-weight:700;color:#f1f5f9;margin:0 0 12px 0;line-height:1.3;">
        {title}
      </h3>
      <div class="price" style="font-size:24px;font-weight:800;color:#4ade80;margin-bottom:8px;">
        {price_str}
      </div>
      <div class="metrics" style="font-size:14px;color:#cbd5e1;margin-bottom:8px;line-height:1.6;">
        <span style="display:inline-block;margin-right:12px;">{mileage_str}</span>
        <span style="display:inline-block;margin-right:12px;color:{deal_pct_color};">{deal_pct_str}</span>
        <span style="display:inline-block;margin-right:12px;color:{savings_color};">{savings_str}</span>
      </div>
      <div class="source" style="font-size:12px;color:#94a3b8;margin-bottom:12px;">
        {source_str}
      </div>
      <a href="{listing['url']}" class="cta-button" style="display:block;width:100%;padding:14px 20px;background:#4ade80;color:#0f172a;text-align:center;text-decoration:none;font-weight:700;font-size:16px;border-radius:8px;min-height:44px;box-sizing:border-box;">
        VIEW LISTING →
      </a>
    </div>"""


def build_mobile_cards(results_by_region: dict, top_pick: dict = None, red_flagged: list = None) -> str:
    """
    Build mobile card layout for all listings.
    Returns HTML string with mobile-cards container and all cards.
    """
    cards_html = '<div class="mobile-cards" style="display:none;padding:16px;">'

    # Add top pick card if exists
    if top_pick:
        cards_html += '<div style="font-size:14px;color:#93c5fd;font-weight:600;letter-spacing:0.05em;margin-bottom:8px;">🔥 TOP PICK TODAY</div>'
        cards_html += build_mobile_card(top_pick)

    # Add red flag section if exists
    if red_flagged:
        cards_html += '''
        <div style="background:linear-gradient(135deg,#7f1d1d 0%,#991b1b 100%);padding:16px;border-radius:8px;margin-bottom:16px;margin-top:16px;">
          <div style="font-size:14px;color:#fca5a5;font-weight:600;letter-spacing:0.05em;margin-bottom:4px;">
            🚩 VERIFY THESE DEALS CAREFULLY
          </div>
          <div style="font-size:11px;color:#fecaca;line-height:1.5;">
            These listings are ≥40% below market price. While they may be legitimate,
            verify carefully for salvage titles, scams, or data errors.
          </div>
        </div>'''

        for listing in red_flagged:
            cards_html += build_mobile_card(listing)

    # Add section header for all listings
    cards_html += '<div style="font-size:14px;color:#e2e8f0;font-weight:700;letter-spacing:0.06em;margin-top:24px;margin-bottom:12px;">📋 ALL LISTINGS BY REGION</div>'

    # Add listings by region
    for region_name, listings in results_by_region.items():
        cards_html += f'<div style="font-size:14px;color:#e2e8f0;font-weight:700;letter-spacing:0.06em;margin-top:16px;margin-bottom:12px;">📍 {region_name}</div>'

        if not listings:
            cards_html += '<div style="padding:14px 0;color:#cbd5e1;font-style:italic;">No new listings found today.</div>'
        else:
            for listing in listings:
                cards_html += build_mobile_card(listing)

    cards_html += '</div>'
    return cards_html



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

async def run(quiet: bool = False):
    # Initialize progress manager and error handler
    progress_mgr = ProgressManager(enabled=not quiet)
    error_handler = ErrorHandler()
    progress_mgr.start()
    
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
                    
                    # Scrape Craigslist with progress and error handling
                    try:
                        with progress_mgr.task(f"🔍 Scraping Craigslist for {make} {model}...") as task:
                            cl_listings = await search_craigslist(context, make, model, years, region, config)
                            raw += cl_listings
                            progress_mgr.update_task(task, f"✓ Craigslist: {len(cl_listings)} listings")
                    except Exception as e:
                        error_handler.record_error("Craigslist", e)
                        log.error(f"Craigslist scraping failed, continuing with other sources...")
                    
                    # Scrape AutoTrader with progress and error handling
                    try:
                        with progress_mgr.task(f"🔍 Scraping AutoTrader for {make} {model}...") as task:
                            at_listings = await search_autotrader(context, make, model, years, region)
                            raw += at_listings
                            progress_mgr.update_task(task, f"✓ AutoTrader: {len(at_listings)} listings")
                    except Exception as e:
                        error_handler.record_error("AutoTrader", e)
                        log.error(f"AutoTrader scraping failed, continuing with other sources...")
                    
                    # Scrape Cars.com with progress and error handling
                    try:
                        with progress_mgr.task(f"🔍 Scraping Cars.com for {make} {model}...") as task:
                            cc_listings = await search_cars_dot_com(context, make, model, years, region)
                            raw += cc_listings
                            progress_mgr.update_task(task, f"✓ Cars.com: {len(cc_listings)} listings")
                    except Exception as e:
                        error_handler.record_error("Cars.com", e)
                        log.error(f"Cars.com scraping failed, continuing with other sources...")
                    
                    # Update total listings found
                    progress_mgr.stats["listings_found"] += len(raw)

                    # Filter and score listings with progress
                    with progress_mgr.task(f"💰 Filtering and scoring {len(raw)} listings...") as task:
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
                        
                        progress_mgr.update_task(task, f"✓ Scored {len(region_listings)} new listings")

                region_listings.sort(key=lambda x: x["score"], reverse=True)
                
                # ── Deep inspection: check title status on listing pages ──
                if region_listings:
                    with progress_mgr.task(f"🔍 Deep inspecting {len(region_listings)} listings...") as task:
                        inspected = await deep_inspect_listings(context, region_listings, concurrency=5)
                        filtered_count = len(region_listings) - len(inspected)
                        region_listings = inspected
                        progress_mgr.update_task(task, f"✓ Deep inspection complete ({len(inspected)} clean, {filtered_count} filtered)")
                        progress_mgr.stats["filtered_count"] += filtered_count
                
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
    
    # Update progress stats
    progress_mgr.stats["api_calls"] = api_stats['live_api_calls']

    total = sum(len(v) for v in results_by_region.values())
    
    # Count good deals for subject line
    good_deal_count = sum(
        1 for listings in results_by_region.values()
        for l in listings
        if l.get("deal_pct") and l.get("deal_pct") >= 15
    )
    
    # Generate subject line using ErrorHandler
    subject = error_handler.get_email_subject(total, good_deal_count)
    
    # Always build and send email (even if no listings or errors occurred)
    html = build_email_html(results_by_region, error_handler)
    send_email(subject, html)
    
    # Save last successful run only if no errors occurred
    if not error_handler.has_errors():
        error_handler.save_last_run()
        log.info(f"\nDone. {total} new listings delivered.")
    else:
        log.warning(f"\nDone with errors. {total} new listings delivered, but some sources failed.")
    
    # Stop progress and print summary
    progress_mgr.stop()
    progress_mgr.print_summary()


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Car Deal Agent - Automated car listing aggregator")
    parser.add_argument('--quiet', action='store_true', help='Disable progress display')
    args = parser.parse_args()

    # Run with parsed arguments
    asyncio.run(run(quiet=args.quiet))



if __name__ == "__main__":
    main()