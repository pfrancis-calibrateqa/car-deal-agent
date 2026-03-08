---
inclusion: manual
---

# Car Search Agent - Technology Stack

## Overview
This application is a Python-based web scraping tool that automatically searches multiple car listing websites, filters results based on configurable criteria, and sends daily email digests of the best deals.

## Core Technologies

### Language & Runtime
- **Python 3.12+** - Modern Python with type hints and async/await support
- **asyncio** - Asynchronous I/O for concurrent web scraping operations

### Web Scraping
- **Playwright 1.58.0** - Browser automation framework
  - Headless Chromium browser for realistic page rendering
  - Network interception for capturing API responses
  - Anti-bot detection measures (custom user agents, random delays)
  - Supports JavaScript-heavy modern websites

### Data Sources
1. **Craigslist** - DOM parsing with fallback to URL slug extraction
2. **AutoTrader** - XHR/API interception with DOM fallback
3. **Cars.com** - Three-tier approach: API interception → JSON-LD schema → DOM

### Email Delivery
- **smtplib** - Python's built-in SMTP client
- **Gmail SMTP** - Uses Gmail's SMTP server with app passwords
- **HTML emails** - Responsive email templates with mobile optimization
- **rich 13.7.0** - Terminal progress display with spinners

### Market Data
- **MarketCheck API** - Vehicle market value data
- **Regional pricing** - ZIP code + radius based pricing
- **Cache system** - JSON cache with live API fallback
- **Deal scoring** - Percentage below/above market calculations

### Configuration & Data
- **JSON** - Configuration files (`search_criteria.json`, `seen_listings.json`)
- **Environment variables** - Sensitive credentials (`.env` file)
- **python-dotenv** - Loads environment variables from `.env`

## Architecture

### Core Components (v2.0)

**ProgressManager** - Real-time execution feedback
- Uses `rich` library for terminal UI
- Spinner animations and status updates
- Final summary with statistics
- `--quiet` flag for automated runs

**ErrorHandler** - Resilient error handling
- Records errors without stopping execution
- Always-send email policy (even on failure)
- Error section in email with troubleshooting
- Last successful run timestamp tracking
- Status-aware email subject lines

**Mobile-Responsive Email** - Card-based mobile layout
- Dual layout: desktop table + mobile cards
- CSS media queries (600px breakpoint)
- Touch-friendly buttons (44px minimum)
- Optimized typography for readability

**DealScorer** - Market value comparison
- MarketCheck API integration
- Regional pricing support (SF Bay Area, Medford)
- Deal grades: Steal, Great Deal, Good Deal, Fair Price, Overpriced
- Cache-based with live API fallback

### Scraping Strategy
Each source uses a tiered extraction approach:

1. **Primary**: Intercept XHR/fetch API calls for clean JSON data
2. **Secondary**: Parse embedded JSON-LD or script tags
3. **Fallback**: DOM parsing with CSS selectors

This approach is resilient to HTML structure changes since APIs are more stable than DOM.

### Anti-Bot Detection
- Custom user agents mimicking real browsers
- Random delays between requests (1.5-3.5 seconds)
- Realistic browser fingerprinting (viewport, locale, timezone)
- HTTP/2 disabled to avoid protocol errors
- Headless mode with webdriver flag hidden

### Data Flow
```
Config (JSON) → Playwright Browser → Multiple Sources (parallel)
    ↓
Raw Listings → Filters (mileage, keywords, colors, years)
    ↓
Deep Inspection (title status, transmission, trim extraction)
    ↓
Deal Scoring (MarketCheck API, regional pricing)
    ↓
Value Scoring (year 40%, mileage 40%, price 20%)
    ↓
Deduplication (hash-based seen tracking)
    ↓
Email Generation (desktop table + mobile cards)
    ↓
Error Handling (always-send policy)
    ↓
Gmail SMTP → User Inbox
```

### Error Handling Flow
```
Try: Scrape Craigslist
  ↓ Success → Add listings
  ↓ Failure → Record error, continue

Try: Scrape AutoTrader
  ↓ Success → Add listings
  ↓ Failure → Record error, continue

Try: Scrape Cars.com
  ↓ Success → Add listings
  ↓ Failure → Record error, continue

Always: Build email (with error section if needed)
Always: Send email (even if all sources failed)
If no errors: Save last successful run timestamp
```

## Key Design Patterns

### Async/Await
All scraping operations use async/await for concurrent execution:
- Multiple regions scraped in parallel
- Browser context reused across searches
- Non-blocking I/O for network requests

### Extraction Functions
Utility functions for parsing unstructured text:
- `extract_year()` - Regex for 4-digit years (1990-2029)
- `extract_mileage()` - Handles "64k mi", "20,500 miles", "odometer: 12345"
- `extract_price()` - Strips non-numeric characters

### Filtering Pipeline
Multi-stage filtering:
1. **Search-time**: URL parameters (year, mileage, drivetrain)
2. **Post-scrape**: Keyword exclusions, color filters, year validation
3. **Deduplication**: MD5 hash of URL to track seen listings

### Scoring Algorithm
Composite value score (0.0 - 1.0):
```python
year_score    = (year - min_year) / (max_year - min_year)  # 40%
mileage_score = 1 - (mileage / max_mileage)                # 40%
price_score   = 1 - (price / 50000)                        # 20%
```

Higher scores indicate better deals (newer, lower mileage, lower price).

## File Structure
```
car-deal-agent/
├── src/
│   ├── search_agent.py       # Main application with ProgressManager, ErrorHandler
│   ├── deal_scorer.py        # MarketCheck API integration
│   ├── car_value_lookup.py   # Market data lookup utilities
│   ├── fetch_car_values.py   # Cache refresh script
│   └── car_values_cache.json # Cached market data
├── config/
│   └── search_criteria.json  # Search configuration with regions
├── data/
│   ├── seen_listings.json    # Deduplication tracking
│   └── last_successful_run.txt # Last successful run timestamp
├── .kiro/
│   ├── specs/                # Feature specifications
│   └── steering/             # Context documentation
├── test_*.py                 # Unit tests
├── .env                      # Credentials (not in git)
├── requirements.txt          # Python dependencies
└── venv/                     # Virtual environment
```

## Configuration Schema

### search_criteria.json
- `searches[]` - Array of make/model/year combinations
- `filters` - Mileage, colors, keywords to exclude
- `regions[]` - Geographic search areas with zip codes
- `ranking` - Scoring methodology

### Environment Variables
- `GMAIL_USER` - Gmail address for sending
- `GMAIL_APP_PASSWORD` - Gmail app-specific password
- `NOTIFY_EMAIL` - Recipient email address

## Deployment Considerations

### Scheduling
Designed to run via cron for daily execution:
```bash
0 8 * * * cd /path/to/project && venv/bin/python src/search_agent.py
```

### Performance
- Typical runtime: 3-5 minutes for 2 regions, 2 makes/models
- Playwright browser overhead: ~100-200MB RAM
- Network-bound (not CPU-intensive)

### Reliability
- Graceful error handling per source (one failure doesn't stop others)
- Timeout protection (30-45 second page load limits)
- Retry logic via random delays and multiple selectors

### Maintenance
- Selectors may break when sites redesign (requires updates)
- API endpoints more stable than DOM structure
- Logging provides visibility into scraping issues

## Security

### Credentials
- Gmail app passwords (not account password)
- Environment variables (never committed to git)
- `.gitignore` protects `.env` file

### Bot Detection Risks
- Craigslist: Moderate (uses delays and realistic headers)
- AutoTrader: Low (API interception is less detectable)
- Cars.com: Low (JSON-LD parsing is passive)

### Rate Limiting
- Random delays prevent aggressive scraping
- Single browser context reused (appears as one session)
- Respects site performance (no parallel requests to same domain)

## Future Enhancements

### Potential Improvements
1. **Facebook Marketplace** - Requires login, more complex bot detection
2. **Market price comparison** - KBB/Edmunds API integration
3. **Description fetching** - Click into listings for full text (slower)
4. **Image analysis** - Computer vision for condition assessment
5. **Historical tracking** - Price trends over time
6. **Mobile notifications** - Push alerts for high-value listings

### Scalability
- Add more sources by implementing source-specific functions
- Parallel region processing (currently sequential)
- Database storage for historical analysis
- Web dashboard for interactive filtering
