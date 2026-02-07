from typing import List, Tuple, Optional, Dict, Any, Union
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

Interval = Tuple[int, int]  # [start, end) in minutes from window start or week start

# Try to get timezone for org (Python 3.9+ has zoneinfo; 3.7 can use backports)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except ImportError:
        ZoneInfo = None  # type: ignore


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


def _parse_iso_datetime(s: str) -> datetime:
    """Parse ISO 8601 datetime string (handles Z and ±HH:MM)."""
    s = s.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _parse_google_event_time(
    start_or_end: Dict[str, str], default_tz: Any = None
) -> datetime:
    """
    Parse Google Calendar API start/end dict to datetime.
    Supports dateTime (ISO) or date (all-day, YYYY-MM-DD).
    For all-day events, default_tz is used (e.g. window_start_dt.tzinfo).
    """
    if "dateTime" in start_or_end:
        return _parse_iso_datetime(start_or_end["dateTime"])
    # All-day: "date": "2024-02-12" -> start of that day in default_tz
    date_str = start_or_end["date"]
    y, m, d = map(int, date_str.split("-"))
    tz = default_tz if default_tz is not None else timezone.utc
    return datetime(y, m, d, 0, 0, 0, tzinfo=tz)


def google_event_to_interval(
    event: Dict[str, Any],
    window_start_dt: datetime,
    window_end_dt: datetime,
) -> Optional[Interval]:
    """
    Convert a Google Calendar API event to (start_min, end_min) relative to window.
    Only returns intervals that overlap the window; events outside the window are clipped.
    """
    default_tz = window_start_dt.tzinfo or timezone.utc
    try:
        start_dt = _parse_google_event_time(event.get("start", {}), default_tz)
        end_dt = _parse_google_event_time(event.get("end", {}), default_tz)
    except (KeyError, ValueError):
        return None
    # Normalize to window timezone for consistent subtraction
    if start_dt.tzinfo != window_start_dt.tzinfo and window_start_dt.tzinfo is not None:
        start_dt = start_dt.astimezone(window_start_dt.tzinfo)
        end_dt = end_dt.astimezone(window_start_dt.tzinfo)
    # Clamp to window
    if end_dt <= window_start_dt or start_dt >= window_end_dt:
        return None
    start_dt = max(start_dt, window_start_dt)
    end_dt = min(end_dt, window_end_dt)
    # Minutes from window start
    start_min = int((start_dt - window_start_dt).total_seconds() // 60)
    end_min = int((end_dt - window_start_dt).total_seconds() // 60)
    if end_min <= start_min:
        return None
    return (start_min, end_min)


def parse_window_datetime(
    dt: Union[datetime, str], org_timezone_str: Optional[str] = None
) -> datetime:
    """
    Parse window boundary from datetime or ISO string.
    If string has no timezone and org_timezone_str is given, interpret in that zone.
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is None and org_timezone_str and ZoneInfo is not None:
            dt = dt.replace(tzinfo=ZoneInfo(org_timezone_str))
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    s = dt.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(s)
    if parsed.tzinfo is None and org_timezone_str and ZoneInfo is not None:
        parsed = parsed.replace(tzinfo=ZoneInfo(org_timezone_str))
    elif parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_people_from_google_events(
    people_events: List[Dict[str, Any]],
    window_start_dt: datetime,
    window_end_dt: datetime,
    org_timezone_str: str = "America/New_York",
) -> List[Person]:
    """
    Build Person list from Google Calendar API–style data.
    Each item in people_events has: id, name, email, timezone, preferences (optional), events (list of Google API event objects).
    Events are converted to (start_min, end_min) relative to the window; only conflicts within the window are used.
    """
    people = []
    default_prefs = PersonPreferences(
        preferred_meeting_times=["morning"],
        avoid_back_to_back=True,
        min_break_minutes=15,
    )
    for p in people_events:
        events_in_window = []
        for ev in p.get("events", []):
            iv = google_event_to_interval(ev, window_start_dt, window_end_dt)
            if iv:
                events_in_window.append(
                    Event(
                        start=iv[0],
                        end=iv[1],
                        timezone=p.get("timezone", org_timezone_str),
                        title=ev.get("summary", ""),
                        description=ev.get("description", ""),
                    )
                )
        prefs_data = p.get("preferences", {})
        prefs = (
            PersonPreferences(
                preferred_meeting_times=prefs_data.get(
                    "preferred_meeting_times", ["morning"]
                ),
                avoid_back_to_back=prefs_data.get("avoid_back_to_back", True),
                min_break_minutes=prefs_data.get("min_break_minutes", 15),
            )
            if prefs_data
            else default_prefs
        )
        people.append(
            Person(
                id=p.get("id", p.get("email", "unknown")),
                name=p.get("name", "Unknown"),
                email=p.get("email", ""),
                events=events_in_window,
                timezone=p.get("timezone", org_timezone_str),
                preferences=prefs,
            )
        )
    return people


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


def _slot_to_day_info(
    slot: Interval, window_start_dt: Optional[datetime] = None
) -> Tuple[int, int, int]:
    """
    Return (start_day_minutes, end_day_minutes, day_of_week) for a slot.
    If window_start_dt is set, slot is minutes from window start; otherwise minutes from week start.
    day_of_week: 0=Monday, 6=Sunday (Python weekday).
    """
    if window_start_dt is not None:
        slot_start_dt = window_start_dt + timedelta(minutes=slot[0])
        slot_end_dt = window_start_dt + timedelta(minutes=slot[1])
        start_day_min = slot_start_dt.hour * 60 + slot_start_dt.minute
        end_day_min = slot_end_dt.hour * 60 + slot_end_dt.minute
        day_of_week = slot_start_dt.weekday()
        return start_day_min, end_day_min, day_of_week
    start_day_min = get_day_minutes(slot[0])
    end_day_min = get_day_minutes(slot[1])
    day_of_week = (slot[0] // 1440) % 7
    return start_day_min, end_day_min, day_of_week


def is_within_work_hours(
    slot: Interval,
    settings: OrgSettings,
    window_start_dt: Optional[datetime] = None,
) -> bool:
    """Check if slot is within work hours."""
    start_day_min, end_day_min, _ = _slot_to_day_info(slot, window_start_dt)

    if end_day_min < start_day_min:
        return False

    return (
        start_day_min >= settings.work_hours_start
        and end_day_min <= settings.work_hours_end
    )


def overlaps_lunch(
    slot: Interval,
    settings: OrgSettings,
    window_start_dt: Optional[datetime] = None,
) -> bool:
    """Check if slot overlaps with lunch window."""
    start_day_min, end_day_min, _ = _slot_to_day_info(slot, window_start_dt)

    return not (
        end_day_min <= settings.lunch_start or start_day_min >= settings.lunch_end
    )


def is_early_or_late(
    slot: Interval,
    settings: OrgSettings,
    window_start_dt: Optional[datetime] = None,
) -> Tuple[bool, bool]:
    """Check if slot is early morning or late evening."""
    start_day_min, end_day_min, _ = _slot_to_day_info(slot, window_start_dt)

    is_early = start_day_min < settings.work_hours_start + 60
    is_late = end_day_min > settings.work_hours_end - 60

    return is_early, is_late


def score_slot(
    slot: Interval,
    settings: OrgSettings,
    location_type: str,
    people: List[Person],
    window_start_dt: Optional[datetime] = None,
) -> ScoredSlot:
    """Score a slot based on multiple feasibility factors."""
    score = 100.0
    reasons = []

    start_day_min, end_day_min, day_of_week = _slot_to_day_info(
        slot, window_start_dt
    )
    hour = start_day_min // 60

    # Get penalties and bonuses from settings
    penalties = settings.penalties
    bonuses = settings.bonuses

    # 1. Work hours check
    if not is_within_work_hours(slot, settings, window_start_dt):
        score -= penalties["outside_work_hours"]
        reasons.append("Outside work hours")

    # 2. Lunch overlap
    if overlaps_lunch(slot, settings, window_start_dt):
        score -= penalties["overlaps_lunch"]
        reasons.append("Overlaps lunch")

    # 3. Early/late penalties
    is_early, is_late = is_early_or_late(slot, settings, window_start_dt)
    if is_early:
        score -= penalties["early_morning"]
        reasons.append("Early morning")
    if is_late:
        score -= penalties["late_evening"]
        reasons.append("Late evening")

    # 4. Time of day preferences
    if 10 <= hour < 11 or 14 <= hour < 15:
        score += bonuses["optimal_time_slot"]
        reasons.append("Optimal time of day")

    # 5. Day of week
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
    if end_day_min == settings.work_hours_end:
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
    window_start_dt: Optional[datetime] = None,
) -> List[ScoredSlot]:
    """Find the top K optimal meeting slots.
    If window_start_dt is set, slots are in minutes from window start and scoring uses real dates.
    """
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
        score_slot(
            slot, settings, location_type, people, window_start_dt=window_start_dt
        )
        for slot in candidates
    ]

    scored_slots.sort(key=lambda x: x.score, reverse=True)

    return scored_slots[:top_k]


def format_time(minutes: int) -> str:
    """Format minutes to readable time string (week-relative: Mon 10:00)."""
    day = minutes // 1440
    day_mins = minutes % 1440
    hour = day_mins // 60
    minute = day_mins % 60

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_name = days[day % 7]

    return f"{day_name} {hour:02d}:{minute:02d}"


def format_slot_datetime(
    slot_start_minutes: int,
    window_start_dt: datetime,
    slot_duration_minutes: Optional[int] = None,
) -> str:
    """Format a slot (minutes from window start) as actual date/time string."""
    slot_start_dt = window_start_dt + timedelta(minutes=slot_start_minutes)
    date_str = slot_start_dt.strftime("%a %Y-%m-%d %H:%M")
    if slot_duration_minutes is not None:
        slot_end_dt = slot_start_dt + timedelta(minutes=slot_duration_minutes)
        date_str += " – " + slot_end_dt.strftime("%H:%M")
    return date_str


def create_meeting_with_dates(
    window_start_dt: Union[datetime, str],
    window_end_dt: Union[datetime, str],
    people_events: List[Dict[str, Any]],
    duration: int = None,
    location_type: str = "virtual",
    org_settings_path: str = "org_settings.json",
    org_timezone_str: Optional[str] = None,
    top_k: int = 5,
) -> List[ScoredSlot]:
    """
    Find optimal meeting slots using exact date window and events in Google Calendar API format.
    Only considers conflicts within the given window.

    Args:
        window_start_dt: Start of search window (datetime or ISO string, e.g. "2024-02-12T09:00:00-05:00")
        window_end_dt: End of search window (datetime or ISO string)
        people_events: List of dicts: id, name, email, timezone, preferences (optional), events (list of Google API event objects with start/end dateTime or date)
        duration: Meeting duration (minutes); if None, uses org_settings default
        location_type: "virtual", "in-person", or "hybrid"
        org_settings_path: Path to org_settings.json
        org_timezone_str: Org timezone (e.g. "America/New_York"); if None, read from org_settings
        top_k: Number of top slots to return

    Returns:
        List of ScoredSlot (start/end in minutes from window start); use format_slot_datetime(slot.start, window_start_dt) for display.
    """
    try:
        with open(org_settings_path, "r") as f:
            org_data = json.load(f)
    except Exception as e:
        raise ValueError(f"Could not load org settings: {e}") from e

    tz_str = org_timezone_str or org_data.get("organization", {}).get(
        "default_timezone", "America/New_York"
    )
    window_start = parse_window_datetime(window_start_dt, tz_str)
    window_end = parse_window_datetime(window_end_dt, tz_str)
    if window_end <= window_start:
        raise ValueError("window_end_dt must be after window_start_dt")

    settings = load_org_settings(org_settings_path)
    if duration is None:
        duration = org_data.get("meeting_preferences", {}).get(
            "default_duration", 60
        )

    people = build_people_from_google_events(
        people_events, window_start, window_end, tz_str
    )
    if not people:
        return []

    window_min = int((window_end - window_start).total_seconds() // 60)
    optimal_slots = find_optimal_slots(
        people=people,
        window_start=0,
        window_end=window_min,
        duration=duration,
        location_type=location_type,
        settings=settings,
        top_k=top_k,
        window_start_dt=window_start,
    )
    return optimal_slots
