# Requirements Document

## Introduction

This document specifies the requirements for integrating the MarketCheck deal scoring system into the car search agent. The integration will enhance the existing car scraper by comparing scraped listings against real market data, providing users with objective deal quality assessments based on national pricing averages.

The system currently has two independent components: a car search agent that scrapes listings from multiple sources, and a deal scoring engine that compares listings against MarketCheck API data. This integration will connect these systems to provide market-based deal grades in the email digest.

## Glossary

- **Search_Agent**: The main car scraping system that collects listings from Craigslist, AutoTrader, and Cars.com
- **Deal_Scorer**: The market value comparison engine that scores listings against MarketCheck API data
- **ScrapedListing**: A data structure representing a car listing extracted from a scraping source
- **DealResult**: A data structure containing market comparison data including grade, savings, and market averages
- **Market_Cache**: A local JSON file (car_values_cache.json) storing recent market data to minimize API calls
- **Deal_Grade**: A categorical assessment of deal quality (e.g., "🔥 Steal", "✅ Great Deal", "⚠️ Overpriced")
- **Email_Digest**: The daily HTML email report sent to users containing new car listings
- **Value_Score**: The existing simple scoring algorithm based on year, mileage, and price
- **MarketCheck_API**: External API service providing real-time used car market data

## Requirements

### Requirement 1: Convert Scraped Listings to Scoring Format

**User Story:** As a developer, I want scraped listings converted to ScrapedListing objects, so that they can be processed by the Deal_Scorer

#### Acceptance Criteria

1. WHEN a listing is scraped from any source, THE Search_Agent SHALL extract all fields required by ScrapedListing (asking_price, year, make, model, mileage, trim, condition, source_url, source_site)
2. THE Search_Agent SHALL create a ScrapedListing object with the extracted fields before scoring
3. IF a required field is missing from the scraped data, THE Search_Agent SHALL set that field to None in the ScrapedListing object
4. THE Search_Agent SHALL normalize the source_site field to lowercase with underscores (e.g., "Cars.com" becomes "cars_com")

### Requirement 2: Score Listings Against Market Data

**User Story:** As a user, I want each listing scored against real market data, so that I can identify genuine deals

#### Acceptance Criteria

1. WHEN a ScrapedListing is created, THE Search_Agent SHALL pass it to Deal_Scorer.score() for market comparison
2. THE Deal_Scorer SHALL first check the Market_Cache for matching vehicle data
3. IF market data is not in the cache, THE Deal_Scorer SHALL fetch it from MarketCheck_API and store it in the cache
4. THE Deal_Scorer SHALL adjust market average price based on mileage difference (±$50 per 1,000 miles delta)
5. THE Deal_Scorer SHALL calculate percentage below/above market and assign a Deal_Grade
6. THE Deal_Scorer SHALL return a DealResult containing grade, savings, market_avg, and data_source

### Requirement 3: Attach Deal Data to Listings

**User Story:** As a developer, I want deal scoring data attached to listing objects, so that it can be displayed in the email

#### Acceptance Criteria

1. WHEN Deal_Scorer returns a DealResult, THE Search_Agent SHALL attach deal_grade, deal_pct, deal_vs_avg, market_avg, and deal_data_src fields to the listing dictionary
2. IF Deal_Scorer returns None (no market data available), THE Search_Agent SHALL set all deal fields to None
3. THE Search_Agent SHALL preserve all existing listing fields when attaching deal data
4. FOR ALL listings, the deal fields SHALL be present (either with values or None) before email generation

### Requirement 4: Display Deal Grades in Email

**User Story:** As a user, I want to see deal grades and market comparison in my email digest, so that I can quickly identify the best deals

#### Acceptance Criteria

1. THE Email_Digest SHALL include a "Deal vs Market" column showing deal grade, percentage vs market, and savings amount
2. WHEN a listing has deal data, THE Email_Digest SHALL display the Deal_Grade emoji and label (e.g., "🔥 Steal")
3. THE Email_Digest SHALL show percentage below/above market with color coding (green for below, red for above, amber for fair)
4. THE Email_Digest SHALL display dollar savings amount (e.g., "save $4,200" or "$1,500 over")
5. THE Email_Digest SHALL show market average price for context (e.g., "mkt avg $27,900")
6. THE Email_Digest SHALL include a regional tag indicating the listing's region (e.g., "[SF]" or "[MED]")
7. WHEN a listing has no deal data, THE Email_Digest SHALL display "— no data" in a neutral color

### Requirement 5: Sort Listings by Deal Quality

**User Story:** As a user, I want listings sorted by deal quality, so that the best deals appear first

#### Acceptance Criteria

1. THE Search_Agent SHALL sort listings by deal_pct (percentage below market) in descending order
2. WHEN a listing has no deal data (deal_pct is None), THE Search_Agent SHALL assign it a sort key of -999 to place it at the end
3. THE Search_Agent SHALL apply deal-based sorting after applying the existing Value_Score
4. THE Email_Digest SHALL display listings in deal quality order within each region

### Requirement 6: Handle Missing Market Data Gracefully

**User Story:** As a user, I want the system to work even when market data is unavailable, so that I still receive my daily digest

#### Acceptance Criteria

1. IF MarketCheck_API is unavailable, THE Deal_Scorer SHALL log a warning and return None
2. IF no API key is configured, THE Deal_Scorer SHALL log a warning and return None without attempting API calls
3. IF a vehicle has no market data (rare model, insufficient listings), THE Deal_Scorer SHALL log a warning and return None
4. WHEN Deal_Scorer returns None, THE Search_Agent SHALL continue processing the listing with deal fields set to None
5. THE Email_Digest SHALL render correctly whether listings have deal data or not
6. THE Search_Agent SHALL complete execution and send the email even if all deal scoring attempts fail

### Requirement 7: Handle API Rate Limits

**User Story:** As a system administrator, I want API calls rate-limited, so that we stay within MarketCheck free tier limits

#### Acceptance Criteria

1. THE Deal_Scorer SHALL add a 0.3 second delay between live API calls when scoring batches
2. THE Deal_Scorer SHALL track the number of live API calls made during execution
3. THE Deal_Scorer SHALL log statistics showing total listings scored and live API calls made
4. IF MarketCheck_API returns a 429 rate limit error, THE Deal_Scorer SHALL log a warning and return None for that listing
5. THE Market_Cache SHALL minimize API calls by storing fetched data for reuse across multiple listings

### Requirement 8: Maintain Cache Performance

**User Story:** As a user, I want fast scraping performance, so that my daily digest arrives promptly

#### Acceptance Criteria

1. THE Deal_Scorer SHALL load the Market_Cache into memory once at initialization
2. THE Deal_Scorer SHALL reuse the in-memory cache for all lookups during a single execution
3. WHEN a cache hit occurs, THE Deal_Scorer SHALL return results without making an API call
4. THE Deal_Scorer SHALL update the Market_Cache file when new data is fetched from the API
5. THE Search_Agent SHALL create a single Deal_Scorer instance and reuse it for all listings in a run

### Requirement 9: Preserve Backward Compatibility

**User Story:** As a user, I want the existing email format preserved, so that I can still use familiar features

#### Acceptance Criteria

1. THE Email_Digest SHALL retain all existing columns (Listing, Price, Miles, Color, Score, Posted)
2. THE Value_Score calculation SHALL remain unchanged and continue to be displayed
3. THE Email_Digest SHALL add the "Deal vs Market" column without removing existing columns
4. THE Search_Agent SHALL continue to apply all existing filters (mileage, keywords, colors)
5. THE Email_Digest footer SHALL document both the Value_Score formula and the Deal vs Market data source

### Requirement 10: Log Integration Activity

**User Story:** As a developer, I want detailed logging of deal scoring activity, so that I can debug issues and monitor API usage

#### Acceptance Criteria

1. THE Deal_Scorer SHALL log each cache hit with the vehicle details
2. THE Deal_Scorer SHALL log each cache miss and subsequent API call
3. THE Deal_Scorer SHALL log when no market data is found for a vehicle
4. THE Deal_Scorer SHALL log final statistics showing total scored and API calls made
5. THE Search_Agent SHALL log the deal scorer statistics after processing all listings
6. WHEN an API error occurs, THE Deal_Scorer SHALL log the error type and HTTP status code
