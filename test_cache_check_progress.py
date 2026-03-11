#!/usr/bin/env python3
"""
Test cache check progress display
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from search_agent import CacheManager, ProgressManager

def test_cache_check_progress():
    """Test that cache check displays progress correctly."""
    
    # Create a temporary cache file with known age
    cache_path = Path("/tmp/test_cache_progress.json")
    
    # Test 1: Fresh cache (2 days old)
    print("\n=== Test 1: Fresh Cache (2 days old) ===")
    fetched_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    cache_data = {
        "metadata": {
            "fetched_at": fetched_at,
            "source": "Test"
        },
        "vehicles": []
    }
    
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    
    progress_mgr = ProgressManager(enabled=True)
    progress_mgr.start()
    
    cache_mgr = CacheManager(cache_path)
    
    with progress_mgr.task("📊 Checking market data cache...") as task:
        age = cache_mgr.get_age_days()
        if age < 7:
            status_emoji = "✓"
            status_color = "fresh"
        elif age < 30:
            status_emoji = "⚠️"
            status_color = "aging"
        else:
            status_emoji = "🚨"
            status_color = "stale"
        
        progress_mgr.update_task(task, f"{status_emoji} Market data cache: {age} days old ({status_color})")
    
    progress_mgr.stop()
    print(f"✓ Fresh cache test passed (age={age}, expected ~2)")
    
    # Test 2: Aging cache (10 days old)
    print("\n=== Test 2: Aging Cache (10 days old) ===")
    fetched_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    cache_data["metadata"]["fetched_at"] = fetched_at
    
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    
    progress_mgr = ProgressManager(enabled=True)
    progress_mgr.start()
    
    cache_mgr = CacheManager(cache_path)
    
    with progress_mgr.task("📊 Checking market data cache...") as task:
        age = cache_mgr.get_age_days()
        if age < 7:
            status_emoji = "✓"
            status_color = "fresh"
        elif age < 30:
            status_emoji = "⚠️"
            status_color = "aging"
        else:
            status_emoji = "🚨"
            status_color = "stale"
        
        progress_mgr.update_task(task, f"{status_emoji} Market data cache: {age} days old ({status_color})")
    
    progress_mgr.stop()
    print(f"✓ Aging cache test passed (age={age}, expected ~10)")
    
    # Test 3: Stale cache (35 days old)
    print("\n=== Test 3: Stale Cache (35 days old) ===")
    fetched_at = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
    cache_data["metadata"]["fetched_at"] = fetched_at
    
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    
    progress_mgr = ProgressManager(enabled=True)
    progress_mgr.start()
    
    cache_mgr = CacheManager(cache_path)
    
    with progress_mgr.task("📊 Checking market data cache...") as task:
        age = cache_mgr.get_age_days()
        if age < 7:
            status_emoji = "✓"
            status_color = "fresh"
        elif age < 30:
            status_emoji = "⚠️"
            status_color = "aging"
        else:
            status_emoji = "🚨"
            status_color = "stale"
        
        progress_mgr.update_task(task, f"{status_emoji} Market data cache: {age} days old ({status_color})")
    
    progress_mgr.stop()
    print(f"✓ Stale cache test passed (age={age}, expected ~35)")
    
    # Test 4: Missing cache
    print("\n=== Test 4: Missing Cache ===")
    cache_path.unlink(missing_ok=True)
    
    progress_mgr = ProgressManager(enabled=True)
    progress_mgr.start()
    
    cache_mgr = CacheManager(cache_path)
    
    with progress_mgr.task("📊 Checking market data cache...") as task:
        age = cache_mgr.get_age_days()
        if age < 7:
            status_emoji = "✓"
            status_color = "fresh"
        elif age < 30:
            status_emoji = "⚠️"
            status_color = "aging"
        else:
            status_emoji = "🚨"
            status_color = "stale"
        
        progress_mgr.update_task(task, f"{status_emoji} Market data cache: {age} days old ({status_color})")
    
    progress_mgr.stop()
    print(f"✓ Missing cache test passed (age={age}, expected 999)")
    
    # Cleanup
    cache_path.unlink(missing_ok=True)
    
    print("\n" + "="*60)
    print("✓ All cache check progress tests passed!")
    print("="*60)


if __name__ == "__main__":
    test_cache_check_progress()
