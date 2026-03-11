#!/usr/bin/env python3
"""
Demo: Cache check progress display
Shows what users will see when the script checks cache age
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from search_agent import CacheManager, ProgressManager

def demo():
    """Demonstrate cache check progress display."""
    
    print("\n" + "="*60)
    print("DEMO: Cache Check Progress Display")
    print("="*60)
    print("\nThis is what users will see when the script checks cache age:\n")
    
    # Use actual cache file
    cache_path = Path(__file__).parent / "src" / "car_values_cache.json"
    
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
    
    print("\n" + "="*60)
    print("Demo complete!")
    print("="*60)


if __name__ == "__main__":
    demo()
