# UAT Improvements - Requirements Document

## Executive Summary

This spec addresses critical usability issues identified during UAT testing of the Car Deal Agent. The improvements focus on execution feedback, mobile experience, error handling, and data freshness - all essential for daily user satisfaction.

## Problem Statement

Current UAT testing revealed four critical issues that significantly impact user experience:

1. **Silent Execution**: Script runs 2-5 minutes with no feedback, causing users to think it's frozen
2. **Mobile Unusability**: Email table layout breaks on mobile devices (60% of email opens)
3. **Hidden Failures**: When scraping fails, users receive no email and no explanation
4. **Stale Market Data**: Regional pricing cache requires manual refresh, leading to inaccurate deal scores

These issues create friction in the daily workflow and reduce trust in the system.

## Goals

1. Provide real-time execution feedback so users know the script is working
2. Make email fully readable and actionable on mobile devices
3. Ensure users always know the status of their daily search, even on failure
4. Automate cache management to maintain accurate regional pricing

## Non-Goals

- Web UI for search management (future phase)
- Listing photo integration (future phase)
- Comparison tools (future phase)
- Market trend analysis (future phase)

---

## Requirement 1: Execution Progress Feedback

### User Story
**As a user**, I want to see real-time progress while the script runs, **so that** I know it's working and not stuck.

### Background
Currently, the script runs silently for 2-5 minutes. Users have no way to know:
- Which source is being scraped
- How many listings have been found
- Whether the script is stuck or just slow
- When deep inspection is happening

This creates anxiety and leads users to kill the process prematurely.

### Acceptance Criteria

**AC1: Source-Level Progress**
- GIVEN the script is running
- WHEN scraping begins for each source (Craigslist, AutoTrader, Cars.com)
- THEN display: "🔍 Scraping [Source]..."
- AND update to: "✓ [Source] complete ([N] listings)" when done

**AC2: Listing Count Updates**
- GIVEN listings are being found
- WHEN each source completes
- THEN display the count of listings found
- AND show cumulative total: "Total: [N] listings across all sources"

**AC3: Deep Inspection Progress**
- GIVEN deep inspection is running
- WHEN inspecting listings for title status/transmission
- THEN display: "🔍 Deep inspecting [N] listings..."
- AND show progress: "[X]/[N] complete"
- AND update in real-time as each listing is inspected

**AC4: Deal Scoring Progress**
- GIVEN deal scoring is running
- WHEN applying market value comparisons
- THEN display: "💰 Scoring deals..."
- AND show: "[X] API calls made" if any cache misses occur

**AC5: Final Summary**
- GIVEN the script has completed
- WHEN all processing is done
- THEN display summary:
  - Total listings found
  - Listings after filtering
  - API calls made
  - Execution time
  - Email sent status

**AC6: Visual Design**
- GIVEN progress is being displayed
- THEN use spinner animation for active tasks
- AND use checkmark (✓) for completed tasks
- AND use colored output (green for success, yellow for warnings, red for errors)
- AND clear previous progress lines (transient display)

### Technical Requirements

**TR1: Progress Library**
- Use `rich` library for terminal formatting
- Implement `Progress` with `SpinnerColumn` and `TextColumn`
- Use transient mode to avoid cluttering terminal

**TR2: Performance**
- Progress updates must not slow down execution
- Maximum 50ms overhead per update
- Use async-safe progress updates

**TR3: Logging Integration**
- Progress display must not interfere with existing logging
- Errors and warnings must still be visible
- Log file must contain all progress information

### Example Output

```
🔍 Scraping Craigslist...
  ✓ sfbay: 8 listings
  ✓ sacramento: 3 listings
  ✓ monterey: 1 listing
✓ Craigslist complete (12 listings)

🔍 Scraping AutoTrader...
✓ AutoTrader complete (7 listings)

🔍 Scraping Cars.com...
✓ Cars.com complete (5 listings)

Total: 24 listings across all sources

🔍 Deep inspecting 24 listings...
  15/24 complete
✓ Deep inspection complete (21 clean listings, 3 filtered)

💰 Scoring deals...
  3 API calls made (cache hits: 18/21)
✓ Deal scoring complete

📊 Summary:
  • Found: 24 listings
  • After filtering: 21 listings
  • API calls: 3
  • Execution time: 2m 34s
  • Email sent: ✓
```

---

## Requirement 2: Mobile-Responsive Email

### User Story
**As a user**, I want to read the email on my phone, **so that** I can check deals while on the go.

### Background
60% of email opens happen on mobile devices. The current table layout:
- Requires horizontal scrolling
- Has tiny, unreadable text
- Makes CTA buttons hard to tap
- Hides critical information off-screen

This makes the email essentially unusable on mobile.

### Acceptance Criteria

**AC1: Responsive Layout Detection**
- GIVEN the email is opened on a device
- WHEN screen width < 600px
- THEN switch from table layout to card layout
- AND hide desktop-only table
- AND show mobile-only cards

**AC2: Card Layout Structure**
- GIVEN mobile card layout is active
- THEN each listing SHALL be displayed as a card with:
  - Deal badge at top (e.g., "🔥 Steal 🚩")
  - Title (year, make, model, trim)
  - Price (large, prominent)
  - Key metrics (mileage, % below market, savings)
  - Source and region
  - CTA button (full width)
- AND cards SHALL have 16px padding
- AND cards SHALL have 12px margin between them
- AND cards SHALL have rounded corners (8px)

**AC3: Typography for Mobile**
- GIVEN mobile layout is active
- THEN font sizes SHALL be:
  - Title: 18px (readable without zoom)
  - Price: 24px (prominent)
  - Metrics: 14px (readable)
  - Source: 12px (secondary info)
- AND line height SHALL be 1.5 for readability
- AND text SHALL NOT require horizontal scrolling

**AC4: Touch Targets**
- GIVEN mobile layout is active
- THEN CTA buttons SHALL be:
  - Minimum 44px height (iOS/Android standard)
  - Full width of card
  - Large, tappable text (16px)
  - Adequate padding (14px vertical, 20px horizontal)

**AC5: Column Prioritization**
- GIVEN mobile layout is active
- THEN show essential columns:
  - Title ✓
  - Price ✓
  - Mileage ✓
  - Deal vs Market ✓
  - CTA button ✓
- AND hide non-essential columns:
  - Color ✗
  - Score ✗
  - Posted date ✗ (show as "Age: 5d" in card)

**AC6: Top Pick Mobile Optimization**
- GIVEN Top Pick section on mobile
- THEN metrics SHALL stack vertically
- AND CTA button SHALL be full width
- AND all text SHALL be readable without zoom

**AC7: Red Flag Section Mobile**
- GIVEN Red Flag section on mobile
- THEN use same card layout as main listings
- AND maintain red gradient background
- AND warning text SHALL wrap properly

### Technical Requirements

**TR1: CSS Media Queries**
```css
@media only screen and (max-width: 600px) {
  .desktop-table { display: none !important; }
  .mobile-card { display: block !important; }
}
```

**TR2: Email Client Compatibility**
- Must work in: Gmail (iOS/Android), Apple Mail, Outlook Mobile
- Use inline CSS (no external stylesheets)
- Avoid CSS features not supported by email clients
- Test with Litmus or Email on Acid

**TR3: Fallback Behavior**
- If media queries not supported, show desktop layout
- Ensure minimum readability even without responsive CSS

### Example Mobile Card

```
┌─────────────────────────────────┐
│ 🔥 Steal 🚩                     │
│                                 │
│ 2021 Honda CR-V Touring         │
│                                 │
│ $21,900                         │
│                                 │
│ 52,000 mi • 17.4% below market  │
│ Save $4,617 • Age: 5d           │
│                                 │
│ Craigslist • SF Bay Area        │
│                                 │
│ ┌─────────────────────────────┐ │
│ │   VIEW LISTING →            │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

---

## Requirement 3: Error Handling and Reporting

### User Story
**As a user**, I want to know when the script fails or finds no listings, **so that** I don't wonder if it ran at all.

### Background
Currently, if scraping fails or finds no listings:
- No email is sent
- No error message is displayed
- User has no way to know what happened
- Logs are the only source of truth (not user-friendly)

This creates uncertainty and reduces trust in the system.

### Acceptance Criteria

**AC1: Always Send Email**
- GIVEN the script has completed execution
- WHEN processing is done (success or failure)
- THEN always send an email
- AND include execution status in email

**AC2: Error Summary Section**
- GIVEN one or more sources failed
- WHEN building the email
- THEN include "⚠️ Scraping Issues" section showing:
  - Which sources failed
  - Error type (timeout, network error, parsing error)
  - Timestamp of failure
- AND use yellow/orange background to indicate warning

**AC3: No Listings Found**
- GIVEN no listings were found
- WHEN all sources returned 0 results
- THEN send email with:
  - "No new listings found today"
  - Possible reasons (too restrictive filters, no new posts)
  - Suggestion to check search criteria
  - Last successful run date

**AC4: Partial Success**
- GIVEN some sources succeeded and some failed
- WHEN building the email
- THEN show successful listings as normal
- AND include error summary at bottom
- AND indicate which regions/sources are missing

**AC5: Email Subject Line Status**
- GIVEN email is being sent
- THEN subject line SHALL indicate status:
  - Success: "Daily Car Deal Digest: 26 listings, 4 great deals"
  - Partial: "Daily Car Deal Digest: 12 listings (⚠️ some sources failed)"
  - No listings: "Daily Car Deal Digest: No new listings today"
  - Complete failure: "Daily Car Deal Digest: ⚠️ Scraping failed"

**AC6: Footer Status Information**
- GIVEN email footer
- THEN include:
  - "Last successful run: [timestamp]"
  - "Next scheduled run: [timestamp]" (if using cron)
  - "Script version: [version]"
  - "Cache age: [N] days old"

**AC7: Retry Guidance**
- GIVEN scraping failed
- WHEN error email is sent
- THEN include troubleshooting tips:
  - "Try running manually: python src/search_agent.py"
  - "Check logs: tail -f logs/search_agent.log"
  - "Verify internet connection"
  - Link to troubleshooting guide

### Technical Requirements

**TR1: Error Tracking**
- Capture all exceptions during scraping
- Store error details (source, error type, timestamp, message)
- Include in email generation context

**TR2: Graceful Degradation**
- If email sending fails, log error and save HTML to file
- If HTML generation fails, send plain text email
- Never fail silently

**TR3: Status Persistence**
- Save last successful run timestamp to file
- Track consecutive failures
- Alert if >3 consecutive failures

### Example Error Email

```
⚠️ SCRAPING ISSUES

Some sources encountered errors:

❌ AutoTrader
   Error: Connection timeout after 45s
   Time: 2026-03-08 08:15:23 PST

❌ Cars.com  
   Error: HTTP 503 Service Unavailable
   Time: 2026-03-08 08:16:45 PST

✓ Craigslist
   Successfully scraped 12 listings

---

📊 Results from available sources:
[Show Craigslist listings here]

---

🔧 Troubleshooting:
• Try running manually: python src/search_agent.py
• Check logs: tail -f logs/search_agent.log
• AutoTrader may be experiencing downtime

Last successful run: 2026-03-07 08:00:15 PST
```

---

## Requirement 4: Automatic Cache Management

### User Story
**As a user**, I want market pricing data to stay current automatically, **so that** deal scores are always accurate.

### Background
Regional pricing cache requires manual refresh via `python src/fetch_car_values.py`. Users forget to run this, leading to:
- Stale market data (30+ days old)
- Inaccurate deal scores
- Misleading "great deal" labels
- Loss of trust in the system

### Acceptance Criteria

**AC1: Cache Age Detection**
- GIVEN the script is starting
- WHEN checking cache file
- THEN determine cache age from metadata.fetched_at
- AND log cache age: "Market data: 3 days old"

**AC2: Automatic Refresh Trigger**
- GIVEN cache age is determined
- WHEN cache is older than 7 days
- THEN automatically trigger cache refresh
- AND log: "Cache is 8 days old, refreshing..."
- AND run fetch_car_values logic inline

**AC3: Stale Cache Warning**
- GIVEN cache age is determined
- WHEN cache is 7-30 days old
- THEN include warning in email footer:
  - "⚠️ Market data is [N] days old"
  - "Prices may not reflect current market"
- AND use yellow warning color

**AC4: Critical Staleness**
- GIVEN cache age is determined
- WHEN cache is >30 days old
- THEN include prominent warning in email:
  - Red banner at top
  - "🚨 Market data is critically outdated ([N] days old)"
  - "Deal scores may be inaccurate"
  - "Refreshing cache automatically..."
- AND force cache refresh regardless of API quota

**AC5: Cache Refresh Progress**
- GIVEN cache refresh is triggered
- WHEN fetching new market data
- THEN show progress:
  - "Refreshing market data..."
  - "[X]/[N] vehicles updated"
  - "API calls: [N]/500 monthly quota"
- AND log any API failures

**AC6: Refresh Failure Handling**
- GIVEN cache refresh fails
- WHEN API is unavailable or quota exceeded
- THEN continue with stale cache
- AND include error in email:
  - "⚠️ Could not refresh market data"
  - "Using [N] day old data"
  - "Reason: [error message]"

**AC7: Cache Age in Email**
- GIVEN email is being generated
- THEN include cache age indicator:
  - Footer: "Market data: 3 days old ✓"
  - Green checkmark if <7 days
  - Yellow warning if 7-30 days
  - Red alert if >30 days

**AC8: Manual Refresh Option**
- GIVEN user wants to force refresh
- WHEN running with --refresh-cache flag
- THEN refresh cache regardless of age
- AND log: "Manual cache refresh requested"

### Technical Requirements

**TR1: Cache Age Calculation**
```python
def get_cache_age_days() -> int:
    cache_file = Path("src/car_values_cache.json")
    if not cache_file.exists():
        return 999  # Force refresh
    
    with open(cache_file) as f:
        data = json.load(f)
    
    fetched_at = data["metadata"]["fetched_at"]
    fetched_dt = datetime.fromisoformat(fetched_at)
    age = (datetime.now(timezone.utc) - fetched_dt).days
    return age
```

**TR2: Inline Refresh**
- Import fetch_car_values logic as module
- Call programmatically instead of subprocess
- Share same logging context

**TR3: API Quota Tracking**
- Track API calls made during refresh
- Warn if approaching monthly limit (500 calls)
- Stop refresh if quota exceeded

**TR4: Atomic Updates**
- Write new cache to temporary file first
- Only replace original on success
- Preserve old cache if refresh fails

### Example Cache Status Display

**Fresh cache (3 days old):**
```
Market data: 3 days old ✓
```

**Aging cache (12 days old):**
```
⚠️ Market data: 12 days old
Prices may not reflect current market
```

**Critical staleness (45 days old):**
```
🚨 MARKET DATA CRITICALLY OUTDATED (45 days old)
Deal scores may be inaccurate. Refreshing automatically...

Refreshing market data...
  15/228 vehicles updated
  API calls: 15/500 monthly quota
✓ Cache refresh complete
```

---

## Success Metrics

### Quantitative Metrics
- **Progress feedback**: 100% of executions show real-time progress
- **Mobile usability**: Email readable on mobile without zooming (measured via user testing)
- **Error visibility**: 100% of failures result in email notification
- **Cache freshness**: Average cache age <7 days

### Qualitative Metrics
- **User confidence**: Users trust that script is running (measured via survey)
- **Mobile satisfaction**: Users can take action from mobile email (measured via survey)
- **Error understanding**: Users know what went wrong when failures occur (measured via support tickets)
- **Data trust**: Users trust deal scores are accurate (measured via survey)

### Performance Metrics
- **Progress overhead**: <50ms per update
- **Mobile email size**: <100KB (acceptable for mobile networks)
- **Cache refresh time**: <2 minutes for full refresh
- **Email send reliability**: >99% success rate

---

## Dependencies

### External Libraries
- `rich` - Terminal progress display (already in requirements.txt)
- No new dependencies required for other features

### API Dependencies
- MarketCheck API - For cache refresh (existing)
- Gmail SMTP - For email sending (existing)

### File Dependencies
- `src/car_values_cache.json` - Market data cache
- `data/seen_listings.json` - Listing history
- `config/search_criteria.json` - Search configuration

---

## Risks and Mitigations

### Risk 1: Email Client Compatibility
**Risk**: Mobile responsive CSS may not work in all email clients
**Mitigation**: 
- Test in top 5 email clients (Gmail, Apple Mail, Outlook, Yahoo, ProtonMail)
- Provide graceful fallback to desktop layout
- Use widely-supported CSS features only

### Risk 2: Progress Display Performance
**Risk**: Progress updates may slow down execution
**Mitigation**:
- Use transient display (clears previous lines)
- Limit update frequency (max 10 updates/second)
- Make progress updates optional via --quiet flag

### Risk 3: Cache Refresh API Quota
**Risk**: Automatic refresh may exhaust monthly API quota
**Mitigation**:
- Only refresh if >7 days old (max 4 refreshes/month)
- Track API calls and warn at 80% quota
- Allow users to disable auto-refresh via config

### Risk 4: Email Sending Failures
**Risk**: Always sending email may cause spam if script fails repeatedly
**Mitigation**:
- Track consecutive failures
- After 3 failures, send summary email instead of individual emails
- Include "Pause notifications" link in error emails

---

## Future Enhancements

These are explicitly out of scope for this spec but noted for future consideration:

1. **Price History Tracking** - Track listing price changes over time
2. **Email Filtering Preferences** - Allow users to filter by trim, deal threshold
3. **Quick Actions** - Save/Dismiss buttons in email
4. **Regional Market Context** - Show how regional pricing compares to national
5. **Listing Photos** - Include thumbnail images in email
6. **Market Trends** - Show 30-day price trends
7. **Web UI** - Browser-based search management
8. **Comparison Tool** - Side-by-side listing comparison

---

## Appendix A: User Research Summary

**UAT Testing Date**: March 8, 2026
**Participants**: 1 primary user (car buyer)
**Testing Duration**: 2 weeks of daily use

**Key Findings**:
1. Silent execution caused anxiety - user killed process 3 times thinking it was stuck
2. Mobile email was "completely unusable" - required desktop to read
3. When scraping failed, user didn't know if script ran or not
4. User didn't know cache needed manual refresh - used 45-day-old data for 2 weeks

**User Quotes**:
- "I have no idea if this is working or frozen"
- "I can't read this on my phone at all"
- "Did it run today? I didn't get an email"
- "How do I know if the prices are current?"

---

## Appendix B: Technical Architecture

### Progress Display Architecture
```
search_agent.py
    ├── Progress (rich library)
    │   ├── SpinnerColumn (animated spinner)
    │   └── TextColumn (status text)
    ├── scrape_craigslist() → update progress
    ├── scrape_autotrader() → update progress
    ├── scrape_cars_com() → update progress
    ├── deep_inspect_listings() → update progress
    └── apply_deal_scores() → update progress
```

### Mobile Email Architecture
```
build_email_html()
    ├── <style> block
    │   ├── Desktop styles (default)
    │   └── @media (max-width: 600px)
    │       ├── .desktop-table { display: none }
    │       └── .mobile-card { display: block }
    ├── Desktop table (class="desktop-table")
    └── Mobile cards (class="mobile-card" style="display:none")
```

### Cache Management Architecture
```
main()
    ├── check_cache_age()
    │   └── return days_old
    ├── if days_old > 7:
    │   └── refresh_cache()
    │       ├── fetch_car_values()
    │       ├── update_cache_file()
    │       └── log_api_usage()
    └── continue with scraping
```

---

## Change Log

| Date | Change | Author | Status |
|------|--------|--------|--------|
| 2026-03-08 | Created UAT improvements spec | System | ✅ Draft Complete |
| 2026-03-08 | Added all 4 P0 requirements | System | ✅ Ready for Review |
