# Car Search Agent

An automated car listing aggregator that searches Craigslist, AutoTrader, and Cars.com for used vehicles matching your criteria, scores each listing against real market values, then emails you a daily digest of the best deals.

## Features

### Core Functionality
- **Multi-source scraping**: Searches Craigslist, AutoTrader, and Cars.com simultaneously
- **Smart filtering**: Filters by year, mileage, color, keywords, and seller type
- **Value scoring**: Ranks listings by a composite score (year 40%, mileage 40%, price 20%)
- **Market deal scoring**: Compares each listing's asking price against national market averages via MarketCheck API — shows grade, % vs market, and dollar savings
- **Mileage-adjusted pricing**: Fair market value is adjusted up/down based on how the listing's mileage compares to the market average
- **Regional flagging**: Listings are tagged [SF] or [MED] so you can contextualize pricing — Bay Area listings typically run above national averages
- **Duplicate detection**: Tracks seen listings to avoid repeat notifications
- **Stealth browsing**: Uses Playwright with anti-bot detection measures

### User Experience (v2.0)
- **Real-time progress display**: Animated spinners and status updates during execution
- **Mobile-responsive email**: Card-based layout optimized for mobile devices (<600px)
- **Error handling**: Always sends email even if some sources fail, with error reporting
- **Status footer**: Shows last successful run, script version, and troubleshooting tips
- **Always-send policy**: Never miss notifications due to scraping failures

### Command-Line Options
- `--quiet` - Disable progress display for automated/cron jobs

## How It Works

### Scraping
The agent uses Playwright to scrape listings with a three-tier extraction strategy:
1. **Network interception**: Captures JSON from XHR/fetch API calls (most reliable)
2. **JSON-LD extraction**: Parses schema.org structured data from page scripts
3. **DOM fallback**: Scrapes HTML elements when other methods fail

### Deal Scoring
After scraping, each listing is run through the deal scorer:

```
Scraped Listing → DealScorer
                       │
          ┌────────────┴────────────┐
          │                        │
    Cache hit?               Cache miss?
  (car_values_cache.json)  (live MarketCheck API)
          │                        │
          └────────────┬───────────┘
                       │
                  DealResult
      { grade, % vs market, savings, market avg }
```

Market data comes from **MarketCheck** — trained on 4M+ recently sold listings from 70,000+ dealerships, updated daily. Free tier: 500 API calls/month, no credit card required.

---

## Setup

### 1. Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
NOTIFY_EMAIL=recipient@gmail.com
MARKETCHECK_API_KEY=your-marketcheck-key
```

**Gmail App Password** (not your regular password):
1. Google Account → Security → Enable 2FA
2. Generate an App Password for "Mail"

**MarketCheck API key** (free):
1. Sign up at https://www.marketcheck.com/signup
2. No credit card required — 500 calls/month on the free tier

### 3. Customize search criteria

Edit `config/search_criteria.json`:

```json
{
  "searches": [
    {
      "make": "Honda",
      "model": "CR-V",
      "years": [2020, 2021, 2022, 2023],
      "drivetrain": "AWD"
    }
  ],
  "filters": {
    "max_mileage": 70000,
    "exclude_colors": ["black"],
    "exclude_keywords": ["salvage", "rebuilt", "as-is"]
  },
  "regions": [
    {
      "name": "San Francisco Bay Area",
      "center_zip": "94102",
      "radius_miles": 100
    },
    {
      "name": "Medford, OR",
      "center_zip": "97501",
      "radius_miles": 75
    }
  ]
}
```

---

## Usage

```bash
python src/search_agent.py
```

The script will:
1. Search all configured sources for matching listings
2. Filter results against your criteria
3. Score each listing (value score + market deal score)
4. Send an email digest with the top 25 listings per region
5. Save seen listings to avoid duplicates on future runs

### Optional: Pre-warm the market value cache

Running this before your first search populates `car_values_cache.json` with
your most-watched makes/models, minimizing live API calls during scraping:

```bash
python src/fetch_car_values.py
```

Edit `VEHICLES_TO_TRACK` in that file to match the cars in your search criteria.

---

## Scheduling

```bash
crontab -e
# Run daily at 8 AM
0 8 * * * cd /path/to/project && /path/to/project/venv/bin/python src/search_agent.py
```

Or via GitHub Actions — see `.github/workflows/daily_search.yml`.

---

## Project Structure

```
.
├── .kiro/
│   └── specs/
│       ├── market-deal-scoring-integration/  # Deal scoring feature spec
│       └── ux-improvements/                  # UX improvements spec
├── config/
│   └── search_criteria.json           # Search configuration
├── data/
│   └── seen_listings.json             # Tracked listings (auto-generated)
├── src/
│   ├── search_agent.py                # Main script
│   ├── deal_scorer.py                 # Market value comparison engine
│   ├── car_values_cache.json          # Local market value store (auto-populated)
│   ├── fetch_car_values.py            # Optional: batch cache pre-warmer
│   ├── car_value_lookup.py            # Optional: standalone cache reader
│   └── example_scraper_integration.py # Optional: integration reference
├── .github/
│   └── workflows/
│       └── daily_search.yml           # GitHub Actions schedule
├── CHANGELOG.md                       # Recent changes and improvements
├── .env                               # Environment variables (create this)
├── requirements.txt
└── README.md
```

---

## Scoring

### Value Score (0–100)
Ranks listings by internal quality metrics — higher is better:

| Factor | Weight | Logic |
|--------|--------|-------|
| Year | 40% | Newer scores higher |
| Mileage | 40% | Fewer miles scores higher |
| Price | 20% | Lower price scores higher (vs $50k ceiling) |

Color-coded in the email: Green >=65 · Yellow >=40 · Red <40

### Deal Score (vs Market)
Compares the asking price to the national market average for that vehicle,
adjusted for mileage:

```
adjusted_market = market_avg + ((market_avg_miles - listing_miles) / 1000 x $50)
pct_below       = (adjusted_market - asking_price) / adjusted_market x 100
```

| Grade | Meaning |
|-------|---------|
| Steal | 20%+ below market |
| Great Deal | 10-20% below market |
| Good Deal | 5-10% below market |
| Fair Price | Within 5% of market |
| Overpriced | 5-10% above market |
| Way Overpriced | 10%+ above market |

**Regional note:** Market averages are national. Bay Area [SF] listings
typically run higher than the national average, so a "Fair Price" tag on an
SF listing may still be competitive locally. Medford [MED] listings running
above national average are a stronger signal to negotiate.

---

## Market Value Cache

The deal scorer reads from `src/car_values_cache.json` (fast, no API call).
On a cache miss it makes a live MarketCheck API call and stores the result
for future lookups — so each unique vehicle is only ever fetched once.

**Free tier math:** 500 calls/month. If you run the scraper daily and search
2 makes x 4 years = 8 vehicle variants, that's ~240 calls/month worst case
(if every variant misses cache every day). Pre-warming the cache with
`fetch_car_values.py` reduces this significantly.

The cache file is safe to commit to git — it contains no secrets, only
publicly available market averages.

---

## Troubleshooting

**Playwright installation issues**
```bash
playwright install --with-deps chromium
```

**Gmail authentication errors**
- Use an App Password, not your regular password
- Ensure 2FA is enabled on your Google account

**No deal scores appearing in email**
- Check that `MARKETCHECK_API_KEY` is set in `.env`
- Run `python src/fetch_car_values.py` to verify the API key works
- Listings without a price or year will always show "no data"

**No listings found**
- Check that search criteria are not too restrictive
- Verify region zip codes are correct
- Review logs for scraping errors

---

## License

MIT