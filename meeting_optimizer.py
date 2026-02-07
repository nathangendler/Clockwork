#!/usr/bin/env python3
"""
Meeting Time Optimizer
Finds optimal meeting times by analyzing multiple calendars from Google Calendar.

Usage:
    python meeting_optimizer.py --start "2024-03-15T09:00:00-05:00" --end "2024-03-15T17:00:00-05:00" --duration 60
"""

import argparse
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path

# Import from your existing scheduler module
from scheduler import (
    create_meeting_with_dates,
    parse_window_datetime,
    format_slot_datetime,
    ScoredSlot,
)


def load_google_calendar_events(calendar_file: str) -> List[Dict[str, Any]]:
    """
    Load calendar events from a JSON file.

    Expected format:
    [
        {
            "id": "person_a",
            "name": "Alice Smith",
            "email": "alice@company.com",
            "timezone": "America/New_York",
            "preferences": {
                "preferred_meeting_times": ["morning"],
                "avoid_back_to_back": true,
                "min_break_minutes": 15
            },
            "events": [
                {
                    "start": {"dateTime": "2024-03-15T10:00:00-05:00"},
                    "end": {"dateTime": "2024-03-15T11:00:00-05:00"},
                    "summary": "Team Standup"
                }
            ]
        }
    ]
    """
    try:
        with open(calendar_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Calendar file '{calendar_file}' not found")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in '{calendar_file}': {e}")
        return []


def print_results(
    slots: List[ScoredSlot],
    window_start_dt: datetime,
    duration: int,
    location_type: str,
    num_people: int,
):
    """Print the optimization results in a readable format."""

    if not slots:
        print("\n❌ No available meeting slots found in the specified time window.")
        print("\nTips:")
        print("  • Try expanding your time window")
        print("  • Consider a shorter meeting duration")
        print("  • Check if all attendees have conflicting events")
        return

    print("\n" + "=" * 70)
    print(f"🎯 OPTIMAL MEETING TIMES FOUND")
    print("=" * 70)
    print(f"\n📊 Search Parameters:")
    print(f"   • Attendees: {num_people} people")
    print(f"   • Duration: {duration} minutes")
    print(f"   • Location: {location_type.title()}")
    print(f"   • Window: {window_start_dt.strftime('%A, %B %d, %Y')}")
    print(f"\n🏆 Top {len(slots)} Recommended Times:\n")

    for i, slot in enumerate(slots, 1):
        time_str = format_slot_datetime(slot.start, window_start_dt, duration)

        # Visual score indicator
        score_bar = "█" * int(slot.score / 10) + "░" * (10 - int(slot.score / 10))

        print(f"{i}. {time_str}")
        print(f"   Score: [{score_bar}] {slot.score:.1f}/100")

        # Categorize reasons
        positives = [
            r
            for r in slot.reasons
            if any(
                word in r.lower()
                for word in ["optimal", "good", "perfect", "fresh", "flexible"]
            )
        ]
        negatives = [r for r in slot.reasons if r not in positives]

        if positives:
            print(f"   ✅ {', '.join(positives)}")
        if negatives:
            print(f"   ⚠️  {', '.join(negatives)}")
        print()

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Find optimal meeting times from Google Calendar data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find 60-min slot today between 9 AM - 5 PM
  python meeting_optimizer.py --start "2024-03-15T09:00:00-05:00" --end "2024-03-15T17:00:00-05:00"
  
  # Find 30-min virtual meeting slot this week
  python meeting_optimizer.py --start "2024-03-15T09:00:00" --end "2024-03-19T17:00:00" --duration 30 --location virtual
  
  # Find top 10 slots for in-person meeting
  python meeting_optimizer.py --start "2024-03-15T09:00:00" --end "2024-03-15T17:00:00" --location in-person --top 10
        """,
    )

    # Required arguments
    parser.add_argument(
        "--start",
        required=True,
        help="Meeting window start time (ISO format: YYYY-MM-DDTHH:MM:SS or with timezone: YYYY-MM-DDTHH:MM:SS-05:00)",
    )

    parser.add_argument(
        "--end", required=True, help="Meeting window end time (ISO format)"
    )

    # Optional arguments
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Meeting duration in minutes (default: 60)",
    )

    parser.add_argument(
        "--location",
        choices=["virtual", "in-person", "hybrid"],
        default="virtual",
        help="Meeting location type (default: virtual)",
    )

    parser.add_argument(
        "--calendars",
        default="calendars/calendars.json",
        help="Path to JSON file with calendar data (default: calendars.json)",
    )

    parser.add_argument(
        "--org-settings",
        default="org_settings.json",
        help="Path to organization settings file (default: org_settings.json)",
    )

    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="Default timezone for parsing dates (default: America/New_York)",
    )

    parser.add_argument(
        "--top", type=int, default=5, help="Number of top slots to return (default: 5)"
    )

    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output results as JSON instead of formatted text",
    )

    args = parser.parse_args()

    # Load calendar data
    print(f"\n🔍 Loading calendar data from '{args.calendars}'...")
    people_events = load_google_calendar_events(args.calendars)

    if not people_events:
        print("❌ No calendar data loaded. Exiting.")
        return 1

    print(f"✅ Loaded calendars for {len(people_events)} people:")
    for person in people_events:
        event_count = len(person.get("events", []))
        print(
            f"   • {person.get('name', 'Unknown')} ({person.get('email', 'no-email')}) - {event_count} events"
        )

    # Parse window times
    try:
        window_start_dt = parse_window_datetime(args.start, args.timezone)
        window_end_dt = parse_window_datetime(args.end, args.timezone)
    except ValueError as e:
        print(f"\n❌ Error parsing dates: {e}")
        print("Please use ISO format: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DDTHH:MM:SS-05:00")
        return 1

    # Validate window
    if window_end_dt <= window_start_dt:
        print("\n❌ Error: End time must be after start time")
        return 1

    window_duration = (window_end_dt - window_start_dt).total_seconds() / 60
    if window_duration < args.duration:
        print(
            f"\n❌ Error: Time window ({window_duration} min) is shorter than meeting duration ({args.duration} min)"
        )
        return 1

    # Run optimization
    print(
        f"\n⚙️  Analyzing availability and optimizing for {args.duration}-minute {args.location} meeting..."
    )

    try:
        optimal_slots = create_meeting_with_dates(
            window_start_dt=args.start,
            window_end_dt=args.end,
            people_events=people_events,
            duration=args.duration,
            location_type=args.location,
            org_settings_path=args.org_settings,
            org_timezone_str=args.timezone,
            top_k=args.top,
        )
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        return 1

    # Output results
    if args.json_output:
        results = {
            "window_start": args.start,
            "window_end": args.end,
            "duration_minutes": args.duration,
            "location_type": args.location,
            "num_attendees": len(people_events),
            "slots": [
                {
                    "start_time": format_slot_datetime(
                        slot.start, window_start_dt, args.duration
                    ),
                    "score": slot.score,
                    "reasons": slot.reasons,
                }
                for slot in optimal_slots
            ],
        }
        print(json.dumps(results, indent=2))
    else:
        print_results(
            optimal_slots,
            window_start_dt,
            args.duration,
            args.location,
            len(people_events),
        )

    return 0


if __name__ == "__main__":
    exit(main())
