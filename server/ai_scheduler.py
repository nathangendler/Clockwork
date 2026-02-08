import os
import json
import google.generativeai as genai
from datetime import datetime
from zoneinfo import ZoneInfo

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def _get_model():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-2.0-flash")


def parse_meeting_request(prompt: str, user_email: str) -> dict:
    """
    Use Gemini to extract structured meeting parameters from a natural language prompt.
    Returns dict with: attendee_names, title, duration_minutes, urgency, location_type,
                       location, time_preference, window_days
    """
    model = _get_model()

    today = datetime.now(ZoneInfo("America/New_York")).strftime("%A, %B %d, %Y")

    system_prompt = f"""You are a meeting scheduling assistant. Extract structured meeting details from the user's request.

Today is {today}. The user's email is {user_email}.

Return ONLY valid JSON with these fields:
- "attendee_names": list of attendee names mentioned (strings). Do NOT include the user themselves.
- "title": a short meeting title (e.g. "Lunch", "Project Sync", "Coffee Chat")
- "duration_minutes": estimated duration as integer. Defaults: lunch=60, coffee=30, meeting=60, quick chat=15
- "urgency": one of "low", "normal", "high". Default "normal".
- "location_type": "in-person" or "virtual". Lunch/coffee/dinner = in-person. Meeting/sync/standup = virtual.
- "location": specific location if mentioned, otherwise empty string
- "time_preference": natural language time hint if any (e.g. "lunchtime", "this afternoon", "morning", "next week"). Empty string if none.
- "window_days": how many days ahead to search for availability. Default 7. If user says "this week" use 5, "today" use 1, "next week" use 14.

Example input: "lunch with john smith"
Example output: {{"attendee_names": ["john smith"], "title": "Lunch", "duration_minutes": 60, "urgency": "normal", "location_type": "in-person", "location": "", "time_preference": "lunchtime", "window_days": 7}}

Example input: "quick zoom call with alice and bob tomorrow morning"
Example output: {{"attendee_names": ["alice", "bob"], "title": "Quick Call", "duration_minutes": 15, "urgency": "normal", "location_type": "virtual", "location": "Zoom", "time_preference": "tomorrow morning", "window_days": 2}}"""

    response = model.generate_content(
        [system_prompt, f"User request: {prompt}"],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    parsed = json.loads(text)

    # Validate and set defaults
    result = {
        "attendee_names": parsed.get("attendee_names", []),
        "title": parsed.get("title", "Meeting"),
        "duration_minutes": int(parsed.get("duration_minutes", 60)),
        "urgency": parsed.get("urgency", "normal"),
        "location_type": parsed.get("location_type", "virtual"),
        "location": parsed.get("location", ""),
        "time_preference": parsed.get("time_preference", ""),
        "window_days": int(parsed.get("window_days", 7)),
    }

    if result["urgency"] not in ("low", "normal", "high"):
        result["urgency"] = "normal"
    if result["location_type"] not in ("in-person", "virtual"):
        result["location_type"] = "virtual"

    return result


def select_best_slot(scored_slots, original_prompt: str, meeting_context: dict) -> int:
    """
    Use Gemini to pick the best slot from the scheduler's top-K candidates,
    given the original user prompt for context (e.g. "lunch" should prefer midday).

    Returns the 0-based index of the best slot.
    """
    if not scored_slots:
        return 0
    if len(scored_slots) == 1:
        return 0

    model = _get_model()
    tz = ZoneInfo("America/New_York")

    slot_descriptions = []
    for i, slot in enumerate(scored_slots):
        start_dt = slot["start_time"]
        end_dt = slot["end_time"]
        if isinstance(start_dt, str):
            start_dt = datetime.fromisoformat(start_dt)
        if isinstance(end_dt, str):
            end_dt = datetime.fromisoformat(end_dt)
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)
        slot_descriptions.append(
            f"{i + 1}. {start_local.strftime('%A, %B %d, %I:%M %p')} - {end_local.strftime('%I:%M %p ET')} (score: {slot['score']:.0f})"
        )

    slots_text = "\n".join(slot_descriptions)

    system_prompt = f"""You are choosing the best meeting time. The user said: "{original_prompt}"

Meeting details:
- Title: {meeting_context.get('title', 'Meeting')}
- Duration: {meeting_context.get('duration_minutes', 60)} minutes
- Type: {meeting_context.get('location_type', 'virtual')}
- Time preference: {meeting_context.get('time_preference', 'none specified')}

Available slots (all times in Eastern Time):
{slots_text}

Consider:
- If the meeting is "lunch", prefer slots around 12pm-1pm
- If "coffee" or "morning", prefer 9am-11am
- If "afternoon", prefer 1pm-4pm
- Higher scores from the scheduling algorithm are generally better
- Respect any explicit time preferences the user stated

Return ONLY a JSON object: {{"slot_number": N}} where N is the 1-based slot number."""

    response = model.generate_content(
        [system_prompt],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    parsed = json.loads(text)
    slot_number = int(parsed.get("slot_number", 1))

    # Convert to 0-based, clamped
    index = max(0, min(slot_number - 1, len(scored_slots) - 1))
    return index
