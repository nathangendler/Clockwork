from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

Interval = Tuple[int, int]  # [start, end) in minutes from reference start


@dataclass
class Event:
    start: int  # minutes from reference start
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

    penalties = settings.penalties
    bonuses = settings.bonuses

    if not is_within_work_hours(slot, settings):
        score -= penalties["outside_work_hours"]
        reasons.append("Outside work hours")

    if overlaps_lunch(slot, settings):
        score -= penalties["overlaps_lunch"]
        reasons.append("Overlaps lunch")

    is_early, is_late = is_early_or_late(slot, settings)
    if is_early:
        score -= penalties["early_morning"]
        reasons.append("Early morning")
    if is_late:
        score -= penalties["late_evening"]
        reasons.append("Late evening")

    start_day_min = get_day_minutes(slot[0])
    hour = start_day_min // 60

    if 10 <= hour < 11 or 14 <= hour < 15:
        score += bonuses["optimal_time_slot"]
        reasons.append("Optimal time of day")

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

    if start_day_min == settings.work_hours_start:
        score -= penalties["no_morning_buffer"]
        reasons.append("No morning buffer")
    if get_day_minutes(slot[1]) == settings.work_hours_end:
        score -= penalties["no_evening_buffer"]
        reasons.append("Runs to end of day")

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


def _start_of_week(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    weekday = dt.weekday()
    start = dt - timedelta(days=weekday)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _to_minutes(dt: datetime, reference: datetime) -> int:
    return int((dt - reference).total_seconds() // 60)


def _parse_event_time(value: Any, reference: datetime) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return _to_minutes(dt, reference)
        except ValueError:
            return None
    return None


def _build_people_from_payload(
    people_payload: List[Dict[str, Any]],
    reference_start: datetime,
) -> List[Person]:
    people: List[Person] = []
    for entry in people_payload:
        events = []
        for event in entry.get("events", []) or []:
            start_min = _parse_event_time(event.get("start"), reference_start)
            end_min = _parse_event_time(event.get("end"), reference_start)
            if start_min is None or end_min is None:
                continue
            events.append(
                Event(
                    start=start_min,
                    end=end_min,
                    timezone=event.get("timezone") or entry.get("timezone") or "UTC",
                    title=event.get("title") or "",
                    description=event.get("description") or "",
                )
            )

        prefs = PersonPreferences(
            preferred_meeting_times=[],
            avoid_back_to_back=False,
            min_break_minutes=0,
        )
        people.append(
            Person(
                id=entry.get("id") or entry.get("email") or "",
                name=entry.get("name") or "",
                email=entry.get("email") or "",
                events=events,
                timezone=entry.get("timezone") or "UTC",
                preferences=prefs,
            )
        )
    return people


def create_meeting_from_payload(
    people_payload: List[Dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
    location_type: str,
    org_settings_path: str,
    top_k: int = 5,
) -> Optional[Tuple[datetime, datetime, List[ScoredSlot]]]:
    """
    Create a meeting using in-memory payload (no files).
    Times are mapped to minutes from the start of the week containing window_start.
    """
    if window_start is None or window_end is None:
        return None

    reference_start = _start_of_week(window_start)
    people = _build_people_from_payload(people_payload, reference_start)
    if not people:
        return None

    settings = load_org_settings(org_settings_path)
    w_start_min = _to_minutes(window_start, reference_start)
    w_end_min = _to_minutes(window_end, reference_start)

    scored = find_optimal_slots(
        people=people,
        window_start=w_start_min,
        window_end=w_end_min,
        duration=duration_minutes,
        location_type=location_type,
        settings=settings,
        top_k=top_k,
    )

    if not scored:
        return None

    best = scored[0]
    start_dt = reference_start + timedelta(minutes=best.start)
    end_dt = reference_start + timedelta(minutes=best.end)
    return start_dt, end_dt, scored

