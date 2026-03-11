# UAT Improvements - Implementation Tasks

## Overview

This task list breaks down the four P0 improvements into actionable implementation steps. Tasks are organized by component and prioritized for sequential execution.

---

## Phase 1: Progress Display (Priority: P0)

### Task 1: Implement ProgressManager Class

**Estimated Time:** 2 hours

#### Subtasks:
- [x] 1.1 Create `ProgressManager` class in `search_agent.py`
  - Add `__init__` method with Console and Progress initialization
  - Add `task()` context manager for spinner tasks
  - Add `update_task()` method for updating task descriptions
  - Add `print_summary()` method for final statistics
  - Add stats tracking dict (listings_found, api_calls, filtered_count)

- [x] 1.2 Add command-line argument support
  - Import `argparse` module
  - Add `--quiet` flag to disable progress display
  - Parse arguments in main()
  - Conditionally create ProgressManager based on flag

- [x] 1.3 Write unit tests
  - Create `test_progress_manager.py`
  - Test task creation and completion
  - Test summary generation
  - Test quiet mode behavior

**Acceptance Criteria:**
- ProgressManager class exists with all methods
- --quiet flag works correctly
- All unit tests pass

---

### Task 2: Integrate Progress Display into Scraping

**Estimated Time:** 3 hours

#### Subtasks:
- [x] 2.1 Add progress to cache check
  - Wrap cache age check in progress.task()
  - Show "Checking cache age..." message
  - Update to show cache age result

- [x] 2.2 Add progress to Craigslist scraping
  - Wrap scrape_craigslist() in progress.task()
  - Show "Scraping Craigslist..." message
  - Update with listing count per subdomain
  - Show final "✓ Craigslist complete (N listings)"

- [x] 2.3 Add progress to AutoTrader scraping
  - Wrap scrape_autotrader() in progress.task()
  - Show "Scraping AutoTrader..." message
  - Update with listing count
  - Show final "✓ AutoTrader complete (N listings)"

- [x] 2.4 Add progress to Cars.com scraping
  - Wrap scrape_cars_com() in progress.task()
  - Show "Scraping Cars.com..." message
  - Update with listing count
  - Show final "✓ Cars.com complete (N listings)"

- [x] 2.5 Add progress to deep inspection
  - Wrap deep_inspect_listings() in progress.task()
  - Show "Deep inspecting N listings..." message
  - Update progress counter: "X/N complete"
  - Show final "✓ Deep inspection complete (N clean, M filtered)"

- [x] 2.6 Add progress to deal scoring
  - Wrap deal scoring loop in progress.task()
  - Show "Scoring deals..." message
  - Track and display API call count
  - Show final "✓ Deal scoring complete"

- [x] 2.7 Add final summary
  - Call progress_mgr.print_summary() at end of main()
  - Display total listings, filtered count, API calls, execution time
  - Show email sent status

**Acceptance Criteria:**
- All scraping operations show progress
- Progress updates in real-time
- Final summary displays correctly
- No performance degradation (< 50ms overhead)

---

### Task 3: Test and Refine Progress Display

**Estimated Time:** 1 hour

#### Subtasks:
- [ ] 3.1 Manual testing
  - Run script and verify all progress messages appear
  - Test with --quiet flag
  - Test with slow network (simulated delays)
  - Verify spinner animations work

- [ ] 3.2 Performance testing
  - Measure execution time with/without progress
  - Verify overhead is <50ms
  - Profile if needed

- [ ] 3.3 User feedback
  - Run with real user and gather feedback
  - Adjust messaging if needed
  - Refine colors/formatting

**Acceptance Criteria:**
- Progress display is clear and helpful
- Performance impact is negligible
- User feedback is positive

---

## Phase 2: Mobile-Responsive Email (Priority: P0)

### Task 4: Implement Mobile Card HTML Generation

**Estimated Time:** 3 hours

#### Subtasks:
- [x] 4.1 Create `build_mobile_cards()` function
  - Accept results_by_region dict
  - Generate mobile-cards container div
  - Loop through regions and listings
  - Return complete mobile HTML

- [x] 4.2 Create `build_mobile_card()` function
  - Accept single listing dict
  - Extract all required fields (title, price, mileage, deal, etc.)
  - Format using format_title_with_trim()
  - Generate card HTML with proper classes
  - Return card HTML string

- [x] 4.3 Add responsive CSS
  - Create `get_responsive_css()` function
  - Add base styles for desktop
  - Add @media query for max-width 600px
  - Style mobile-card, deal-badge, listing-title, price, metrics, source, cta-button
  - Ensure proper display toggling (desktop-table vs mobile-cards)

- [x] 4.4 Modify `build_email_html()` function
  - Add viewport meta tag
  - Include responsive CSS in <style> block
  - Generate both desktop table and mobile cards
  - Combine into single HTML document

**Acceptance Criteria:**
- Mobile cards generate correctly
- CSS switches layouts at 600px breakpoint
- All listing data displays in cards

---

### Task 5: Optimize Mobile Layout

**Estimated Time:** 2 hours

#### Subtasks:
- [x] 5.1 Optimize Top Pick for mobile
  - Make metrics stack vertically on mobile
  - Ensure CTA button is full width
  - Test readability on small screens

- [x] 5.2 Optimize Red Flag section for mobile
  - Apply card layout to red-flagged listings
  - Maintain red gradient background
  - Ensure warning text wraps properly

- [x] 5.3 Add mobile-specific typography
  - Increase font sizes for readability
  - Adjust line heights (1.5-1.6)
  - Ensure no text requires zooming

- [x] 5.4 Optimize touch targets
  - Ensure CTA buttons are min 44px height
  - Add adequate padding around tappable elements
  - Test on actual mobile devices

**Acceptance Criteria:**
- Top Pick displays well on mobile
- Red Flag section displays well on mobile
- All text is readable without zooming
- All buttons are easily tappable

---

### Task 6: Test Mobile Email Compatibility

**Estimated Time:** 2 hours

#### Subtasks:
- [ ] 6.1 Test in Gmail
  - Test on Gmail iOS app
  - Test on Gmail Android app
  - Test on Gmail web (mobile view)
  - Document any issues

- [ ] 6.2 Test in Apple Mail
  - Test on iPhone Mail app
  - Test on iPad Mail app
  - Test on macOS Mail (mobile view)
  - Document any issues

- [ ] 6.3 Test in Outlook
  - Test on Outlook iOS app
  - Test on Outlook Android app
  - Test on Outlook web (mobile view)
  - Document any issues

- [ ] 6.4 Test in other clients
  - Test Yahoo Mail mobile
  - Test ProtonMail mobile
  - Document any issues

- [ ] 6.5 Fix compatibility issues
  - Address any rendering problems
  - Add fallbacks for unsupported CSS
  - Retest after fixes

**Acceptance Criteria:**
- Email renders correctly in top 5 email clients
- Fallback to desktop layout works if media queries unsupported
- No critical rendering issues

---

## Phase 3: Error Handling (Priority: P0)

### Task 7: Implement ErrorHandler Class

**Estimated Time:** 2 hours

#### Subtasks:
- [x] 7.1 Create `ScrapingError` dataclass
  - Add fields: source, error_type, message, timestamp
  - Import dataclass and datetime

- [x] 7.2 Create `ErrorHandler` class
  - Add `__init__` with errors list and last_successful_run
  - Add `record_error()` method
  - Add `has_errors()` method
  - Add `build_error_section()` method for HTML
  - Add `get_email_subject()` method
  - Add `save_last_run()` and `load_last_run()` methods

- [x] 7.3 Create last run persistence file
  - Create data/last_successful_run.txt
  - Add to .gitignore
  - Implement file read/write logic

- [x] 7.4 Write unit tests
  - Create `test_error_handler.py`
  - Test error recording
  - Test error section HTML generation
  - Test subject line generation
  - Test last run persistence

**Acceptance Criteria:**
- ErrorHandler class exists with all methods
- Last run timestamp persists correctly
- All unit tests pass

---

### Task 8: Integrate Error Handling into Scraping

**Estimated Time:** 2 hours

#### Subtasks:
- [x] 8.1 Add try-catch to Craigslist scraping
  - Wrap scrape_craigslist() in try-except
  - Call error_handler.record_error() on exception
  - Log error but continue execution
  - Don't let exception stop script

- [x] 8.2 Add try-catch to AutoTrader scraping
  - Wrap scrape_autotrader() in try-except
  - Call error_handler.record_error() on exception
  - Log error but continue execution

- [x] 8.3 Add try-catch to Cars.com scraping
  - Wrap scrape_cars_com() in try-except
  - Call error_handler.record_error() on exception
  - Log error but continue execution

- [x] 8.4 Modify email generation
  - Always call build_email_html() even if no listings
  - Include error_handler.build_error_section() in HTML
  - Use error_handler.get_email_subject() for subject line

- [x] 8.5 Implement always-send logic
  - Remove conditional email sending
  - Always call send_email() at end of main()
  - Handle case of 0 listings gracefully
  - Save last run timestamp only on success

**Acceptance Criteria:**
- Script continues even if sources fail
- Email always sent regardless of success/failure
- Error section appears in email when errors occur
- Subject line reflects status correctly

---

### Task 9: Add Email Footer Status

**Estimated Time:** 1 hour

#### Subtasks:
- [x] 9.1 Add footer status section
  - Create footer HTML template
  - Include last successful run timestamp
  - Include cache age indicator
  - Include script version

- [x] 9.2 Add troubleshooting tips
  - Add "No listings found" guidance
  - Add error troubleshooting steps
  - Add links to documentation

- [x] 9.3 Test footer display
  - Verify footer appears in all email scenarios
  - Test with errors
  - Test with no listings
  - Test with successful run

**Acceptance Criteria:**
- Footer displays in all emails
- Last run timestamp is accurate
- Troubleshooting tips are helpful

---

## Phase 4: Cache Management (Priority: P0)

### Task 10: Implement CacheManager Class

**Estimated Time:** 2 hours

#### Subtasks:
- [x] 10.1 Create `CacheManager` class
  - Add `__init__` with cache_path parameter
  - Add `get_age_days()` method
  - Add `needs_refresh()` method with threshold parameter
  - Add `get_status_html()` method for email footer
  - Add `refresh()` method

- [x] 10.2 Refactor fetch_car_values.py
  - Extract fetch_and_cache() function for programmatic use
  - Make it importable from search_agent.py
  - Ensure it works both standalone and imported

- [x] 10.3 Write unit tests
  - Create `test_cache_manager.py`
  - Test age calculation
  - Test needs_refresh logic
  - Test status HTML generation
  - Mock fetch_and_cache for refresh testing

**Acceptance Criteria:**
- CacheManager class exists with all methods
- fetch_car_values is importable
- All unit tests pass

---

### Task 11: Integrate Cache Auto-Refresh

**Estimated Time:** 2 hours

#### Subtasks:
- [x] 11.1 Add cache check to main()
  - Create CacheManager instance
  - Call get_age_days() at script start
  - Log cache age

- [x] 11.2 Implement auto-refresh logic
  - Check if needs_refresh() returns True
  - Call cache_mgr.refresh() if needed
  - Pass progress_mgr for progress display
  - Handle refresh failures gracefully

- [x] 11.3 Add cache status to email footer
  - Call cache_mgr.get_status_html()
  - Include in footer section
  - Color-code based on age (green/yellow/red)

- [x] 11.4 Add manual refresh flag
  - Add --refresh-cache command-line argument
  - Force refresh regardless of age when flag present
  - Log manual refresh request

**Acceptance Criteria:**
- Cache auto-refreshes when >7 days old
- Cache status displays in email footer
- Manual refresh flag works correctly
- Refresh failures don't stop script

---

### Task 12: Test Cache Management

**Estimated Time:** 1 hour

#### Subtasks:
- [ ] 12.1 Test auto-refresh trigger
  - Manually set cache to 8 days old
  - Run script and verify refresh triggers
  - Verify new cache is written

- [ ] 12.2 Test refresh failure handling
  - Simulate API failure
  - Verify script continues with stale cache
  - Verify error appears in email

- [ ] 12.3 Test manual refresh
  - Run with --refresh-cache flag
  - Verify refresh happens regardless of age
  - Verify progress display works

- [ ] 12.4 Test cache status display
  - Test with fresh cache (<7 days)
  - Test with aging cache (7-30 days)
  - Test with stale cache (>30 days)
  - Verify colors and messages are correct

**Acceptance Criteria:**
- Auto-refresh works correctly
- Failures are handled gracefully
- Manual refresh works
- Status display is accurate

---

## Phase 5: Integration and Testing (Priority: P0)

### Task 13: Integration Testing

**Estimated Time:** 2 hours

#### Subtasks:
- [ ] 13.1 Test complete flow with all components
  - Run script with all features enabled
  - Verify progress display works
  - Verify mobile email generates
  - Verify error handling works
  - Verify cache management works

- [ ] 13.2 Test edge cases
  - Test with no listings found
  - Test with all sources failing
  - Test with partial source failures
  - Test with stale cache
  - Test with fresh cache

- [ ] 13.3 Test performance
  - Measure total execution time
  - Verify no significant slowdown
  - Profile if needed

- [ ] 13.4 Test on actual mobile devices
  - Send test email to mobile
  - Open on iPhone
  - Open on Android
  - Verify readability and usability

**Acceptance Criteria:**
- All components work together correctly
- No regressions in existing functionality
- Performance is acceptable
- Mobile email is usable

---

### Task 14: Documentation Updates

**Estimated Time:** 2 hours

#### Subtasks:
- [ ] 14.1 Update README.md
  - Add section on progress display
  - Document --quiet flag
  - Document --refresh-cache flag
  - Explain cache auto-refresh
  - Add mobile email screenshot
  - Update troubleshooting section

- [ ] 14.2 Update CHANGELOG.md
  - Document all four improvements
  - Include before/after examples
  - Note any breaking changes
  - Add migration guide if needed

- [ ] 14.3 Update requirements.md spec
  - Mark all requirements as completed
  - Add implementation notes
  - Document any deviations from spec

- [ ] 14.4 Create troubleshooting guide
  - Add section on progress display issues
  - Add section on mobile email rendering
  - Add section on error email interpretation
  - Add section on cache refresh failures

**Acceptance Criteria:**
- All documentation is up to date
- Examples are clear and accurate
- Troubleshooting guide is comprehensive

---

### Task 15: User Acceptance Testing

**Estimated Time:** 1 hour

#### Subtasks:
- [ ] 15.1 Run with real user
  - Have user run script with new features
  - Observe their experience
  - Gather feedback

- [ ] 15.2 Test mobile email with user
  - Send email to user's mobile device
  - Have them open and interact with it
  - Gather feedback on usability

- [ ] 15.3 Test error scenarios with user
  - Simulate failures
  - Have user interpret error emails
  - Gather feedback on clarity

- [ ] 15.4 Refine based on feedback
  - Address any usability issues
  - Improve messaging if needed
  - Make final adjustments

**Acceptance Criteria:**
- User can successfully use all new features
- User understands error messages
- User finds mobile email usable
- User is satisfied with improvements

---

## Summary

**Total Estimated Time:** 30 hours (approximately 1 week of full-time work)

**Task Breakdown:**
- Phase 1 (Progress Display): 6 hours
- Phase 2 (Mobile Email): 7 hours
- Phase 3 (Error Handling): 5 hours
- Phase 4 (Cache Management): 5 hours
- Phase 5 (Integration & Testing): 5 hours
- Documentation: 2 hours

**Dependencies:**
- Tasks within each phase should be completed sequentially
- Phases can be completed in order (1 → 2 → 3 → 4 → 5)
- Integration testing (Phase 5) requires all previous phases complete

**Success Criteria:**
- All 15 tasks completed
- All unit tests passing
- All integration tests passing
- User acceptance testing successful
- Documentation complete and accurate

---

## Notes

- Each task should be tested individually before moving to the next
- Commit after each completed task
- Run full test suite after each phase
- Get user feedback early and often
- Be prepared to iterate based on feedback
