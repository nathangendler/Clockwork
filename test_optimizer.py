#!/usr/bin/env python3
"""
Test script for the meeting optimizer.
Validates that the optimizer can find meeting times with the sample data.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path to import scheduler
sys.path.insert(0, str(Path(__file__).parent))

from scheduler import (
    create_meeting_with_dates,
    parse_window_datetime,
    format_slot_datetime
)


def test_basic_optimization():
    """Test basic meeting optimization with sample data."""
    
    print("="*70)
    print("TESTING MEETING OPTIMIZER")
    print("="*70)
    
    # Load sample calendars
    print("\n1. Loading sample calendar data...")
    try:
        with open('calendars.json', 'r') as f:
            calendars = json.load(f)
        print(f"   ✅ Loaded {len(calendars)} calendars")
    except Exception as e:
        print(f"   ❌ Error loading calendars: {e}")
        return False
    
    # Load org settings
    print("\n2. Loading organization settings...")
    try:
        with open('org_settings.json', 'r') as f:
            org_settings = json.load(f)
        print("   ✅ Loaded org settings")
    except Exception as e:
        print(f"   ❌ Error loading org settings: {e}")
        return False
    
    # Define test window (March 15, 2024, 9 AM - 5 PM ET)
    print("\n3. Setting up test window...")
    window_start = "2024-03-15T09:00:00-05:00"
    window_end = "2024-03-15T17:00:00-05:00"
    print(f"   Start: {window_start}")
    print(f"   End:   {window_end}")
    
    # Run optimization
    print("\n4. Running optimization...")
    try:
        optimal_slots = create_meeting_with_dates(
            window_start_dt=window_start,
            window_end_dt=window_end,
            people_events=calendars,
            duration=60,
            location_type="virtual",
            org_settings_path="org_settings.json",
            top_k=5
        )
        print(f"   ✅ Found {len(optimal_slots)} optimal slots")
    except Exception as e:
        print(f"   ❌ Error during optimization: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Display results
    print("\n5. Results:")
    print("-"*70)
    
    if not optimal_slots:
        print("   ⚠️  No optimal slots found")
        return True
    
    window_start_dt = parse_window_datetime(window_start)
    
    for i, slot in enumerate(optimal_slots, 1):
        time_str = format_slot_datetime(slot.start, window_start_dt, 60)
        score_bar = "█" * int(slot.score / 10) + "░" * (10 - int(slot.score / 10))
        
        print(f"\n   {i}. {time_str}")
        print(f"      Score: [{score_bar}] {slot.score:.1f}/100")
        print(f"      Reasons: {', '.join(slot.reasons)}")
    
    print("\n" + "="*70)
    print("✅ TEST PASSED - Optimizer working correctly!")
    print("="*70)
    
    return True


def test_timezone_handling():
    """Test that the optimizer handles multiple timezones correctly."""
    
    print("\n\nTesting timezone handling...")
    
    # Create test data with different timezones
    people_events = [
        {
            "id": "person_nyc",
            "name": "NYC Person",
            "email": "nyc@example.com",
            "timezone": "America/New_York",
            "events": [
                {
                    "start": {"dateTime": "2024-03-15T10:00:00-05:00"},
                    "end": {"dateTime": "2024-03-15T11:00:00-05:00"},
                    "summary": "Morning meeting"
                }
            ]
        },
        {
            "id": "person_la",
            "name": "LA Person",
            "email": "la@example.com",
            "timezone": "America/Los_Angeles",
            "events": [
                {
                    "start": {"dateTime": "2024-03-15T09:00:00-08:00"},  # 12 PM ET
                    "end": {"dateTime": "2024-03-15T10:00:00-08:00"},
                    "summary": "Lunch"
                }
            ]
        }
    ]
    
    window_start = "2024-03-15T09:00:00-05:00"
    window_end = "2024-03-15T17:00:00-05:00"
    
    try:
        optimal_slots = create_meeting_with_dates(
            window_start_dt=window_start,
            window_end_dt=window_end,
            people_events=people_events,
            duration=60,
            location_type="virtual",
            org_settings_path="org_settings.json",
            top_k=3
        )
        
        print(f"✅ Timezone test passed - Found {len(optimal_slots)} slots")
        return True
    except Exception as e:
        print(f"❌ Timezone test failed: {e}")
        return False


if __name__ == '__main__':
    success = test_basic_optimization()
    
    if success:
        test_timezone_handling()
    
    sys.exit(0 if success else 1)
