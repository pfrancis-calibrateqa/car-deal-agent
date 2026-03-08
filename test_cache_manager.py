#!/usr/bin/env python3
"""
Unit tests for CacheManager class
"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from search_agent import CacheManager


def test_get_age_days_fresh_cache():
    """Test age calculation for a fresh cache (< 1 day old)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_data = {
            "metadata": {
                "fetched_at": datetime.now(timezone.utc).isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        age = cache_mgr.get_age_days()
        
        assert age == 0, f"Expected age 0, got {age}"
        print("✓ test_get_age_days_fresh_cache passed")
    finally:
        cache_path.unlink()


def test_get_age_days_old_cache():
    """Test age calculation for an old cache (7 days old)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        cache_data = {
            "metadata": {
                "fetched_at": seven_days_ago.isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        age = cache_mgr.get_age_days()
        
        assert age == 7, f"Expected age 7, got {age}"
        print("✓ test_get_age_days_old_cache passed")
    finally:
        cache_path.unlink()


def test_get_age_days_missing_cache():
    """Test age calculation when cache file doesn't exist."""
    cache_path = Path("/tmp/nonexistent_cache_file.json")
    cache_mgr = CacheManager(cache_path)
    age = cache_mgr.get_age_days()
    
    assert age == 999, f"Expected age 999 for missing cache, got {age}"
    print("✓ test_get_age_days_missing_cache passed")


def test_get_age_days_missing_timestamp():
    """Test age calculation when cache is missing fetched_at timestamp."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_data = {
            "metadata": {},
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        age = cache_mgr.get_age_days()
        
        assert age == 999, f"Expected age 999 for missing timestamp, got {age}"
        print("✓ test_get_age_days_missing_timestamp passed")
    finally:
        cache_path.unlink()


def test_needs_refresh_fresh_cache():
    """Test needs_refresh returns False for fresh cache."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_data = {
            "metadata": {
                "fetched_at": datetime.now(timezone.utc).isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        needs_refresh = cache_mgr.needs_refresh(threshold_days=7)
        
        assert not needs_refresh, "Fresh cache should not need refresh"
        print("✓ test_needs_refresh_fresh_cache passed")
    finally:
        cache_path.unlink()


def test_needs_refresh_old_cache():
    """Test needs_refresh returns True for old cache."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        ten_days_ago = datetime.now(timezone.utc) - timedelta(days=10)
        cache_data = {
            "metadata": {
                "fetched_at": ten_days_ago.isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        needs_refresh = cache_mgr.needs_refresh(threshold_days=7)
        
        assert needs_refresh, "Old cache should need refresh"
        print("✓ test_needs_refresh_old_cache passed")
    finally:
        cache_path.unlink()


def test_needs_refresh_custom_threshold():
    """Test needs_refresh with custom threshold."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
        cache_data = {
            "metadata": {
                "fetched_at": five_days_ago.isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        
        # Should not need refresh with 7-day threshold
        assert not cache_mgr.needs_refresh(threshold_days=7), "Should not need refresh with 7-day threshold"
        
        # Should need refresh with 3-day threshold
        assert cache_mgr.needs_refresh(threshold_days=3), "Should need refresh with 3-day threshold"
        
        print("✓ test_needs_refresh_custom_threshold passed")
    finally:
        cache_path.unlink()


def test_get_status_html_fresh():
    """Test status HTML for fresh cache (< 7 days)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_data = {
            "metadata": {
                "fetched_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        html = cache_mgr.get_status_html()
        
        assert "color:#4ade80" in html, "Fresh cache should be green"
        assert "3 days old" in html, "Should show correct age"
        print("✓ test_get_status_html_fresh passed")
    finally:
        cache_path.unlink()


def test_get_status_html_warning():
    """Test status HTML for warning cache (7-29 days)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_data = {
            "metadata": {
                "fetched_at": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        html = cache_mgr.get_status_html()
        
        assert "color:#fbbf24" in html, "Warning cache should be yellow"
        assert "15 days old" in html, "Should show correct age"
        print("✓ test_get_status_html_warning passed")
    finally:
        cache_path.unlink()


def test_get_status_html_critical():
    """Test status HTML for critical cache (>= 30 days)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_data = {
            "metadata": {
                "fetched_at": (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
            },
            "vehicles": []
        }
        json.dump(cache_data, f)
        cache_path = Path(f.name)
    
    try:
        cache_mgr = CacheManager(cache_path)
        html = cache_mgr.get_status_html()
        
        assert "color:#ef4444" in html, "Critical cache should be red"
        assert "35 days old" in html, "Should show correct age"
        assert "critically outdated" in html, "Should show critical warning"
        print("✓ test_get_status_html_critical passed")
    finally:
        cache_path.unlink()


def test_get_status_html_missing():
    """Test status HTML for missing cache."""
    cache_path = Path("/tmp/nonexistent_cache_file.json")
    cache_mgr = CacheManager(cache_path)
    html = cache_mgr.get_status_html()
    
    assert "color:#ef4444" in html, "Missing cache should be red"
    assert "Not found" in html, "Should show 'Not found' message"
    print("✓ test_get_status_html_missing passed")


def test_refresh_success():
    """Test successful cache refresh."""
    cache_path = Path("/tmp/test_cache.json")
    cache_mgr = CacheManager(cache_path)
    
    # Mock subprocess.run to simulate successful refresh
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        
        # Should not raise exception
        cache_mgr.refresh(progress_mgr=None)
        
        # Verify subprocess was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["python", "src/fetch_car_values.py"]
        
        print("✓ test_refresh_success passed")


def test_refresh_failure():
    """Test cache refresh failure handling."""
    cache_path = Path("/tmp/test_cache.json")
    cache_mgr = CacheManager(cache_path)
    
    # Mock subprocess.run to simulate failed refresh
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="API error")
        
        # Should raise RuntimeError
        try:
            cache_mgr.refresh(progress_mgr=None)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Cache refresh failed" in str(e)
            print("✓ test_refresh_failure passed")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Running CacheManager Unit Tests")
    print("="*60 + "\n")
    
    test_get_age_days_fresh_cache()
    test_get_age_days_old_cache()
    test_get_age_days_missing_cache()
    test_get_age_days_missing_timestamp()
    test_needs_refresh_fresh_cache()
    test_needs_refresh_old_cache()
    test_needs_refresh_custom_threshold()
    test_get_status_html_fresh()
    test_get_status_html_warning()
    test_get_status_html_critical()
    test_get_status_html_missing()
    test_refresh_success()
    test_refresh_failure()
    
    print("\n" + "="*60)
    print("✅ All CacheManager tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
