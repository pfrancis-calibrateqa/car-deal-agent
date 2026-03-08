#!/usr/bin/env python3
"""
Unit tests for ErrorHandler class.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

sys.path.insert(0, 'src')

from search_agent import ErrorHandler, ScrapingError


def test_error_recording():
    """Test that errors are recorded correctly."""
    handler = ErrorHandler()
    
    # Record a test error
    try:
        raise ValueError("Test error message")
    except Exception as e:
        handler.record_error("Craigslist", e)
    
    # Verify error was recorded
    assert handler.has_errors()
    assert len(handler.errors) == 1
    assert handler.errors[0].source == "Craigslist"
    assert handler.errors[0].error_type == "ValueError"
    assert "Test error message" in handler.errors[0].message
    assert isinstance(handler.errors[0].timestamp, datetime)
    
    print("✓ Error recording test passed")


def test_error_section_html():
    """Test error section HTML generation."""
    handler = ErrorHandler()
    
    # No errors - should return empty string
    assert handler.build_error_section() == ""
    
    # Add an error
    try:
        raise ConnectionError("Network timeout")
    except Exception as e:
        handler.record_error("AutoTrader", e)
    
    # Generate HTML
    html = handler.build_error_section()
    
    # Verify HTML contains expected elements
    assert "⚠️ SCRAPING ISSUES" in html
    assert "AutoTrader" in html
    assert "ConnectionError" in html
    assert "Network timeout" in html
    assert "Troubleshooting" in html
    
    print("✓ Error section HTML test passed")


def test_email_subject_generation():
    """Test email subject line generation."""
    handler = ErrorHandler()
    
    # No errors, with listings
    subject = handler.get_email_subject(10, 3)
    assert "10 listings" in subject
    assert "3 great deals" in subject
    assert "⚠️" not in subject
    
    # With errors, with listings
    try:
        raise Exception("Test error")
    except Exception as e:
        handler.record_error("Cars.com", e)
    
    subject = handler.get_email_subject(5, 1)
    assert "5 listings" in subject
    assert "⚠️ some sources failed" in subject
    
    # No errors, no listings
    handler2 = ErrorHandler()
    subject = handler2.get_email_subject(0, 0)
    assert "No new listings today" in subject
    
    # With errors, no listings
    handler3 = ErrorHandler()
    try:
        raise Exception("Test error")
    except Exception as e:
        handler3.record_error("Craigslist", e)
    
    subject = handler3.get_email_subject(0, 0)
    assert "⚠️ Scraping failed" in subject
    
    print("✓ Email subject generation test passed")


def test_last_run_persistence():
    """Test last run timestamp persistence."""
    # Create a temporary directory for testing
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Create handler with custom file path
        handler = ErrorHandler()
        handler.last_run_file = temp_dir / "test_last_run.txt"
        
        # Save timestamp
        handler.save_last_run()
        
        # Verify file was created
        assert handler.last_run_file.exists()
        
        # Create new handler and load timestamp
        handler2 = ErrorHandler()
        handler2.last_run_file = temp_dir / "test_last_run.txt"
        handler2.load_last_run()
        
        # Verify timestamp was loaded
        assert handler2.last_successful_run is not None
        assert isinstance(handler2.last_successful_run, datetime)
        
        # Timestamps should be very close (within 1 second)
        time_diff = abs((datetime.now() - handler2.last_successful_run).total_seconds())
        assert time_diff < 2
        
        print("✓ Last run persistence test passed")
        
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir)


def test_multiple_errors():
    """Test handling multiple errors from different sources."""
    handler = ErrorHandler()
    
    # Record multiple errors
    errors_to_record = [
        ("Craigslist", ValueError("Invalid data")),
        ("AutoTrader", ConnectionError("Timeout")),
        ("Cars.com", RuntimeError("Unexpected response"))
    ]
    
    for source, error in errors_to_record:
        handler.record_error(source, error)
    
    # Verify all errors were recorded
    assert len(handler.errors) == 3
    assert handler.has_errors()
    
    # Verify HTML contains all errors
    html = handler.build_error_section()
    assert "Craigslist" in html
    assert "AutoTrader" in html
    assert "Cars.com" in html
    assert "ValueError" in html
    assert "ConnectionError" in html
    assert "RuntimeError" in html
    
    print("✓ Multiple errors test passed")


if __name__ == "__main__":
    print("Running ErrorHandler tests...\n")
    
    test_error_recording()
    test_error_section_html()
    test_email_subject_generation()
    test_last_run_persistence()
    test_multiple_errors()
    
    print("\n✅ All ErrorHandler tests passed!")
