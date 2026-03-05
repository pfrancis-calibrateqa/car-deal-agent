# Car Search Agent

An automated car listing aggregator that searches Craigslist, AutoTrader, and Cars.com for used vehicles matching your criteria, then emails you a daily digest of the best deals.

## Features

- **Multi-source scraping**: Searches Craigslist, AutoTrader, and Cars.com simultaneously
- **Smart filtering**: Filters by year, mileage, color, keywords, and seller type
- **Value scoring**: Ranks listings by a composite score (year 40%, mileage 40%, price 20%)
- **Duplicate detection**: Tracks seen listings to avoid repeat notifications
- **Email digest**: Sends a styled HTML email with top results
- **Stealth browsing**: Uses Playwright with anti-bot detection measures

## How It Works

The agent uses Playwright to scrape listings with a three-tier extraction strategy:
1. **Network interception**: Captures JSON from XHR/fetch API calls (most reliable)
2. **JSON-LD extraction**: Parses schema.org structured data from page scripts
3. **DOM fallback**: Scrapes HTML elements when other methods fail

## Setup

### 1. Install Python dependencies

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
NOTIFY_EMAIL=recipient@gmail.com
```

**Note**: You'll need to generate a Gmail App Password (not your regular password):
1. Go to Google Account settings → Security
2. Enable 2-factor authentication
3. Generate an App Password for "Mail"

### 3. Customize search criteria

Edit `config/search_criteria.json` to define:
- **Makes/models**: Which vehicles to search for
- **Years**: Specific model years
- **Filters**: Max mileage, excluded colors, excluded keywords
- **Regions**: Search locations with zip codes and radius

Example:
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
    }
  ]
}
```

## Usage

Run the search agent:

```bash
python src/search_agent.py
```

The script will:
1. Search all configured sources for matching listings
2. Filter and score results
3. Send an email digest with the top 25 listings per region
4. Save seen listings to avoid duplicates on future runs

## Scheduling

To run automatically, set up a cron job:

```bash
# Edit crontab
crontab -e

# Run daily at 8 AM
0 8 * * * cd /path/to/project && /path/to/project/venv/bin/python src/search_agent.py
```

## Project Structure

```
.
├── config/
│   └── search_criteria.json    # Search configuration
├── data/
│   └── seen_listings.json      # Tracked listings (auto-generated)
├── src/
│   └── search_agent.py         # Main script
├── .env                        # Environment variables (create this)
├── .gitignore
├── requirements.txt
└── README.md
```

## Value Score Calculation

Each listing receives a score from 0-1 based on:
- **Year (40%)**: Newer vehicles score higher
- **Mileage (40%)**: Lower mileage scores higher
- **Price (20%)**: Lower prices score higher (relative to $50k ceiling)

Scores are color-coded in the email:
- 🟢 Green (≥65): Excellent deal
- 🟡 Yellow (≥40): Good deal
- 🔴 Red (<40): Fair deal

## Troubleshooting

**Playwright installation issues**:
```bash
playwright install --with-deps chromium
```

**Gmail authentication errors**:
- Verify you're using an App Password, not your regular password
- Ensure 2FA is enabled on your Google account

**No listings found**:
- Check that your search criteria aren't too restrictive
- Verify the regions and zip codes are correct
- Review logs for scraping errors

## License

MIT
