"""
example_scraper_integration.py
================================
Shows how your scraper plugs into DealScorer.
Replace the `simulate_scraped_listings()` function with your real scraper output.

Run:  python example_scraper_integration.py
"""

import json
import logging
from deal_scorer import DealScorer, ScrapedListing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def simulate_scraped_listings() -> list[ScrapedListing]:
    """
    Stand-in for your real scraper. In production, replace this with
    whatever your CL / FB Marketplace scraper produces.

    Your scraper should map its raw fields to ScrapedListing:
        ScrapedListing(
            asking_price = int(raw["price"].replace("$","").replace(",","")),
            year         = int(raw["year"]),
            make         = raw["make"],
            model        = raw["model"],
            mileage      = int(raw["odometer"]) if raw.get("odometer") else None,
            trim         = raw.get("trim"),
            condition    = raw.get("condition"),
            source_url   = raw["url"],
            source_site  = "craigslist",
        )
    """
    return [
        # Great deal — 2021 Camry LE, low miles, $4k under market
        ScrapedListing(
            asking_price=19500, year=2021, make="Toyota", model="Camry",
            mileage=28000, trim="LE", condition="clean",
            source_url="https://honolulu.craigslist.org/cto/d/camry/1234567.html",
            source_site="craigslist", listing_id="cl-1234567"
        ),
        # Overpriced — same car but seller wants too much
        ScrapedListing(
            asking_price=29900, year=2021, make="Toyota", model="Camry",
            mileage=35000, trim="LE", condition="clean",
            source_url="https://honolulu.craigslist.org/cto/d/camry/7654321.html",
            source_site="craigslist", listing_id="cl-7654321"
        ),
        # Good deal — Honda Civic, slightly high miles
        ScrapedListing(
            asking_price=20500, year=2022, make="Honda", model="Civic",
            mileage=31000, trim="EX", condition="clean",
            source_url="https://www.facebook.com/marketplace/item/abc123",
            source_site="facebook_marketplace", listing_id="fb-abc123"
        ),
        # Steal — Tesla well below market
        ScrapedListing(
            asking_price=28000, year=2021, make="Tesla", model="Model 3",
            mileage=40000, trim="Long Range", condition="clean",
            source_url="https://honolulu.craigslist.org/cto/d/tesla/9999999.html",
            source_site="craigslist", listing_id="cl-9999999"
        ),
        # Salvage title — condition flag should appear
        ScrapedListing(
            asking_price=22000, year=2020, make="Ford", model="F-150",
            mileage=55000, trim="XLT", condition="salvage",
            source_url="https://honolulu.craigslist.org/cto/d/f150/5555555.html",
            source_site="craigslist", listing_id="cl-5555555"
        ),
        # Cache miss scenario — not in cache, triggers live API call
        ScrapedListing(
            asking_price=24000, year=2022, make="Mazda", model="CX-5",
            mileage=22000, trim="Touring", condition="clean",
            source_url="https://honolulu.craigslist.org/cto/d/cx5/8888888.html",
            source_site="craigslist", listing_id="cl-8888888"
        ),
    ]


def print_results(results: list):
    print("\n" + "═" * 60)
    print("  DEAL SCORING RESULTS")
    print("═" * 60)

    # Sort best deals first
    results.sort(key=lambda r: r.pct_below_market, reverse=True)

    for r in results:
        print(f"\n{r.summary()}")
        if r.source_url:
            print(f"  🔗 {r.source_url}")
        print("─" * 60)

    # Summary table
    print(f"\n{'VEHICLE':<35} {'ASKING':>9} {'MARKET AVG':>10} {'DELTA':>9} {'GRADE'}")
    print("-" * 80)
    for r in results:
        vehicle = f"{r.year} {r.make} {r.model} {r.trim or ''}".strip()[:34]
        delta   = f"{'+' if r.pct_below_market < 0 else '-'}{abs(r.pct_below_market):.1f}%"
        print(
            f"{vehicle:<35} "
            f"${r.asking_price:>8,.0f} "
            f"${r.market_avg:>9,.0f} "
            f"{delta:>9}  "
            f"{r.grade}"
        )


def save_results(results: list, path: str = "scored_listings.json"):
    with open(path, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    print(f"\n✓ Full results saved to {path}")


if __name__ == "__main__":
    scorer   = DealScorer()
    listings = simulate_scraped_listings()
    results  = scorer.score_batch(listings)

    print_results(results)
    save_results(results, "scored_listings.json")

    api_stats = scorer.stats()
    print(f"\nAPI usage this run: {api_stats['live_api_calls']} live calls "
          f"({api_stats['scored']} total scored from cache or API)")
