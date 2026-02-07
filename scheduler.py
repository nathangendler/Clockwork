from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path

Interval = Tuple[int, int]  # [start, end) in minutes from epoch or week start


@dataclass
class Event:
    start: int  # minutes
    end: int
    timezone: str
    title: str = ""
    description: str = ""


@dataclass
class PersonPreferences:
    preferred_meeting_times: List[str]
    avoid_back_to_back: bool
    min_break_minutes: int


@dataclass
class Person:
    id: str
    name: str
    email: str
    events: List[Event]
    timezone: str
    preferences: PersonPreferences


@dataclass
class OrgSettings:
    work_hours_start: int
    work_hours_end: int
    lunch_start: int
    lunch_end: int
    penalties: Dict[str, float]
    bonuses: Dict[str, float]
    interval_minutes: int = 15


@dataclass
class ScoredSlot:
    start: int
    end: int
    score: float
    reasons: List[str]


def load_person_from_file(filepath: str) -> Person:
    """Load a person's calendar data from JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)

    return Person(
        id=data["id"],
        name=data["name"],
        email=data["email"],
        timezone=data["timezone"],
        events=[Event(**e) for e in data["events"]],
        preferences=PersonPreferences(**data["preferences"]),
    )


def load_org_settings(filepath: str) -> OrgSettings:
    """Load organization settings from JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)

    return OrgSettings(
        work_hours_start=data["work_hours"]["start"],
        work_hours_end=data["work_hours"]["end"],
        lunch_start=data["lunch_window"]["start"],
        lunch_end=data["lunch_window"]["end"],
        penalties=data["penalties"],
        bonuses=data["bonuses"],
        interval_minutes=data["meeting_preferences"]["interval_minutes"],
    )


def discover_all_people(people_dir: str = "people") -> List[str]:
    """
    Automatically discover all person JSON files in the people directory.

    Args:
        people_dir: Directory containing person JSON files

    Returns:
        List of person IDs (filenames without .json extension)
    """
    people_path = Path(people_dir)
    if not people_path.exists():
        print(f"✗ Warning: People directory '{people_dir}' not found")
        return []

    person_files = list(people_path.glob("*.json"))
    person_ids = [f.stem for f in person_files if f.is_file()]
    
    print(f"✓ Discovered {len(person_ids)} person files in '{people_dir}' directory")
    return person_ids


def aggregate_people_data(person_ids: List[str] = None, data_dir: str = "people") -> List[Person]:
    """
    Aggregate calendar data from multiple people.
    If person_ids is None, automatically discovers all files in the people directory.

    Args:
        person_ids: List of person IDs to invite (if None, discovers all)
        data_dir: Directory containing person JSON files

    Returns:
        List of Person objects with their calendar data
    """
    people = []
    data_path = Path(data_dir)

    # If person_ids is None, discover all people
    if person_ids is None:
        person_ids = discover_all_people(data_dir)

    for person_id in person_ids:
        filepath = data_path / f"{person_id}.json"
        if filepath.exists():
            try:
                person = load_person_from_file(str(filepath))
                people.append(person)
                print(f"✓ Loaded calendar for {person.name} ({person.email})")
            except Exception as e:
                print(f"✗ Error loading {person_id}: {e}")
        else:
            print(f"✗ Warning: Calendar file not found for {person_id}")

    return people


def clip_interval(iv: Interval, w_start: int, w_end: int) -> Optional[Interval]:
    s, e = iv
    s2 = max(s, w_start)
    e2 = min(e, w_end)
    if e2 <= s2:
        return None
    return (s2, e2)


def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    """Merge overlapping/touching intervals."""
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def busy_to_free(busy: List[Interval], w_start: int, w_end: int) -> List[Interval]:
    """Given merged busy intervals, return free intervals."""
    free: List[Interval] = []
    cur = w_start
    for s, e in busy:
        if s > cur:
            free.append((cur, s))
        cur = e
        if cur >= w_end:
            break
    if cur < w_end:
        free.append((cur, w_end))
    return free


def get_all_busy_intervals(
    people: List[Person], window_start: int, window_end: int
) -> List[Interval]:
    """Collect and merge all busy intervals from all people."""
    all_busy = []
    for person in people:
        for event in person.events:
            clipped = clip_interval((event.start, event.end), window_start, window_end)
            if clipped:
                all_busy.append(clipped)
    return merge_intervals(all_busy)


def generate_candidate_slots(
    free_intervals: List[Interval], duration: int, interval_minutes: int = 15
) -> List[Interval]:
    """Generate candidate slots on configured boundaries within free intervals."""
    candidates = []

    for free_start, free_end in free_intervals:
        first_start = (
            (free_start + interval_minutes - 1) // interval_minutes
        ) * interval_minutes

        current = first_start
        while current + duration <= free_end:
            candidates.append((current, current + duration))
            current += interval_minutes

    return candidates


def get_day_minutes(minutes_from_ref: int) -> int:
    """Get minutes from start of day (0-1439)."""
    return minutes_from_ref % 1440


def is_within_work_hours(slot: Interval, settings: OrgSettings) -> bool:
    """Check if slot is within work hours."""
    start_day_min = get_day_minutes(slot[0])
    end_day_min = get_day_minutes(slot[1])

    if end_day_min < start_day_min:
        return False

    return (
        start_day_min >= settings.work_hours_start
        and end_day_min <= settings.work_hours_end
    )


def overlaps_lunch(slot: Interval, settings: OrgSettings) -> bool:
    """Check if slot overlaps with lunch window."""
    start_day_min = get_day_minutes(slot[0])
    end_day_min = get_day_minutes(slot[1])

    return not (
        end_day_min <= settings.lunch_start or start_day_min >= settings.lunch_end
    )


def is_early_or_late(slot: Interval, settings: OrgSettings) -> Tuple[bool, bool]:
    """Check if slot is early morning or late evening."""
    start_day_min = get_day_minutes(slot[0])
    end_day_min = get_day_minutes(slot[1])

    is_early = start_day_min < settings.work_hours_start + 60
    is_late = end_day_min > settings.work_hours_end - 60

    return is_early, is_late


def score_slot(
    slot: Interval, settings: OrgSettings, location_type: str, people: List[Person]
) -> ScoredSlot:
    """Score a slot based on multiple feasibility factors."""
    score = 100.0
    reasons = []

    # Get penalties and bonuses from settings
    penalties = settings.penalties
    bonuses = settings.bonuses

    # 1. Work hours check
    if not is_within_work_hours(slot, settings):
        score -= penalties["outside_work_hours"]
        reasons.append("Outside work hours")

    # 2. Lunch overlap
    if overlaps_lunch(slot, settings):
        score -= penalties["overlaps_lunch"]
        reasons.append("Overlaps lunch")

    # 3. Early/late penalties
    is_early, is_late = is_early_or_late(slot, settings)
    if is_early:
        score -= penalties["early_morning"]
        reasons.append("Early morning")
    if is_late:
        score -= penalties["late_evening"]
        reasons.append("Late evening")

    # 4. Time of day preferences
    start_day_min = get_day_minutes(slot[0])
    hour = start_day_min // 60

    if 10 <= hour < 11 or 14 <= hour < 15:
        score += bonuses["optimal_time_slot"]
        reasons.append("Optimal time of day")

    # 5. Day of week
    day_of_week = (slot[0] // 1440) % 7
    if day_of_week >= 5:
        score -= penalties["weekend"]
        reasons.append("Weekend")
    elif day_of_week == 0:
        score += bonuses["monday_morning"]
        reasons.append("Monday (fresh start)")
    elif day_of_week == 4:
        score -= penalties["friday_afternoon"]
        reasons.append("Friday (end of week)")

    # 6. Location type
    if location_type == "in-person":
        if 10 <= hour < 15:
            score += bonuses["in_person_midday"]
            reasons.append("Good time for in-person")
        if hour < 9:
            score -= 10
            reasons.append("Too early for in-person")
    elif location_type == "virtual":
        score += bonuses["virtual_meeting"]
        reasons.append("Virtual (flexible)")

    # 7. Buffer time
    if start_day_min == settings.work_hours_start:
        score -= penalties["no_morning_buffer"]
        reasons.append("No morning buffer")
    if get_day_minutes(slot[1]) == settings.work_hours_end:
        score -= penalties["no_evening_buffer"]
        reasons.append("Runs to end of day")

    # 8. Multiple timezones
    unique_timezones = len(set(p.timezone for p in people))
    if unique_timezones > 1:
        score -= (unique_timezones - 1) * penalties["per_additional_timezone"]
        reasons.append(f"{unique_timezones} timezones")

    if not reasons:
        reasons.append("Perfect slot")

    return ScoredSlot(start=slot[0], end=slot[1], score=max(0, score), reasons=reasons)


def find_optimal_slots(
    people: List[Person],
    window_start: int,
    window_end: int,
    duration: int,
    location_type: str,
    settings: OrgSettings,
    top_k: int = 5,
) -> List[ScoredSlot]:
    """Find the top K optimal meeting slots."""
    busy_intervals = get_all_busy_intervals(people, window_start, window_end)
    free_intervals = busy_to_free(busy_intervals, window_start, window_end)

    if not free_intervals:
        return []

    candidates = generate_candidate_slots(
        free_intervals, duration, settings.interval_minutes
    )

    if not candidates:
        return []

    scored_slots = [
        score_slot(slot, settings, location_type, people) for slot in candidates
    ]

    scored_slots.sort(key=lambda x: x.score, reverse=True)

    return scored_slots[:top_k]


def format_time(minutes: int) -> str:
    """Format minutes to readable time string."""
    day = minutes // 1440
    day_mins = minutes % 1440
    hour = day_mins // 60
    minute = day_mins % 60

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_name = days[day % 7]

    return f"{day_name} {hour:02d}:{minute:02d}"


def create_meeting(
    invitee_ids: List[str] = None,
    window_start: int = None,
    window_end: int = None,
    duration: int = None,
    location_type: str = "virtual",
    people_dir: str = "people",
    org_settings_path: str = "org_settings.json",
    top_k: int = 5,
) -> List[ScoredSlot]:
    """
    Main function to create a meeting by aggregating invitees' calendars.
    If invitee_ids is None, automatically uses all people in the people directory.

    Args:
        invitee_ids: List of person IDs to invite (if None, uses all people)
        window_start: Start of search window (minutes from epoch or week start)
        window_end: End of search window (minutes from epoch or week start)
        duration: Meeting duration (minutes)
        location_type: "virtual", "in-person", or "hybrid"
        people_dir: Directory containing person JSON files
        org_settings_path: Path to organization settings JSON file
        top_k: Number of top slots to return

    Returns:
        List of top K scored meeting slots
    """
    print(f"\n{'='*60}")
    if invitee_ids is None:
        print("Creating meeting with ALL people in the people folder")
    else:
        print(f"Creating meeting with {len(invitee_ids)} invitees")
    print(f"{'='*60}\n")

    # Step 1: Aggregate calendar data from invitees (or all people)
    print("📅 Fetching calendar data...")
    people = aggregate_people_data(invitee_ids, people_dir)

    if not people:
        print("❌ No valid calendars found!")
        return []

    print(f"\n✓ Successfully loaded {len(people)} calendars\n")

    # Step 2: Load org settings
    print("⚙️  Loading organization settings...")
    try:
        settings = load_org_settings(org_settings_path)
        print(f"✓ Loaded organization settings from {org_settings_path}\n")
    except Exception as e:
        print(f"❌ Error loading org settings: {e}")
        return []

    # Step 3: Use default values from org settings if not provided
    if duration is None:
        # Try to get from org_settings.json
        try:
            with open(org_settings_path, "r") as f:
                org_data = json.load(f)
                duration = org_data.get("meeting_preferences", {}).get("default_duration", 60)
        except:
            duration = 60  # Fallback to 60 minutes

    if window_start is None or window_end is None:
        # Default to next week's work hours
        DAY = 1440
        window_start = 7 * DAY + settings.work_hours_start  # Next Monday 9am
        window_end = 11 * DAY + settings.work_hours_end    # Next Friday 5pm
        print(f"ℹ️  Using default window: Next week's work hours\n")

    # Step 4: Find optimal slots
    print("🔍 Finding optimal meeting times...")
    optimal_slots = find_optimal_slots(
        people=people,
        window_start=window_start,
        window_end=window_end,
        duration=duration,
        location_type=location_type,
        settings=settings,
        top_k=top_k,
    )

    return optimal_slots


# -----------------------
# Example usage
# -----------------------
if __name__ == "__main__":
    DAY = 1440

    # Automatically get all people from the people folder
    # and find optimal slots based on org_settings.json
    optimal_slots = create_meeting(
        invitee_ids=None,  # None = use all people in people/ folder
        window_start=None,  # None = use default from org settings
        window_end=None,    # None = use default from org settings
        duration=None,      # None = use default from org settings
        location_type="virtual",
        people_dir="people",
        org_settings_path="org_settings.json",
        top_k=10,
    )

    if optimal_slots:
        print(f"\n{'='*60}")
        print(f"Top {len(optimal_slots)} optimal slots found")
        print(f"{'='*60}\n")

        for i, slot in enumerate(optimal_slots, 1):
            print(f"{i}. {format_time(slot.start)} - {format_time(slot.end)}")
            print(f"   Score: {slot.score:.1f}/100")
            print(f"   Reasons: {', '.join(slot.reasons)}")
            print()
    else:
        print("\n❌ No optimal slots found. Try adjusting the time window or duration.")
