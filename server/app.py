from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
import json
from zoneinfo import ZoneInfo
from flask_cors import CORS

load_dotenv()

from flask import Flask, redirect, request, session, render_template, jsonify
from flask_cors import CORS

from auth import (
    get_authorization_url,
    handle_callback,
    get_session,
    get_people_service,
    get_user_by_email,
    get_calendar_service,
    get_calendar_service_for_user,
)
from db import (
    init_db,
    SessionLocal,
    User,
    MeetingProposal,
    ConfirmedMeeting,
    MeetingInvite,
    ConfirmedMeetingInvite,
    Notification,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")


def get_auth_token():
    """
    Get authentication token from either:
    1. Flask session cookie (browser dev mode)
    2. Authorization Bearer header (Chrome extension)
    """
    # Check session cookie first
    token = session.get("session_token")
    if token:
        return token

    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix

    return None

CORS(app, supports_credentials=True, origins=[
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "chrome-extension://<YOUR_EXTENSION_ID>"
])

app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
)

# ===== Scheduling helpers =====

DEFAULT_TIMEZONE = "America/New_York"


def _parse_datetime(value, field_name, assume_tz=ZoneInfo("America/New_York")):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=assume_tz)
        return value.astimezone(assume_tz)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=assume_tz)
            return dt.astimezone(assume_tz)
        except ValueError as exc:
            raise ValueError(f"invalid {field_name} datetime") from exc
    raise ValueError(f"invalid {field_name} datetime")

def _build_participant_payload(user, timezone_name, events=None):
    return {
        "id": f"user_{user.id}",
        "name": user.name or "",
        "email": user.email,
        "timezone": timezone_name,
        "events": events or [],
    }


def _format_log_time(value):
    if value is None:
        return "None"
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt.astimezone(ZoneInfo("America/New_York"))
    formatted = local_dt.strftime("%Y-%m-%d %I:%M %p %Z")
    return formatted.lstrip("0").replace(" 0", " ")


def _normalize_google_event(event, fallback_timezone):
    start = event.get("start", {})
    end = event.get("end", {})
    start_dt = start.get("dateTime") or start.get("date")
    end_dt = end.get("dateTime") or end.get("date")

    if not start_dt or not end_dt:
        return None

    if len(start_dt) == 10:
        start_dt = f"{start_dt}T00:00:00Z"
    if len(end_dt) == 10:
        end_dt = f"{end_dt}T00:00:00Z"

    return {
        "start": start_dt,
        "end": end_dt,
        "timezone": start.get("timeZone") or fallback_timezone,
        "title": event.get("summary", "") or "",
        "description": event.get("description", "") or "",
    }


def _get_calendar_events_for_user(user_id, time_min, time_max, fallback_timezone):
    if not time_min or not time_max:
        return []
    service = get_calendar_service_for_user(user_id)
    if not service:
        return []

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception:
        return []

    events = []
    for event in result.get("items", []):
        normalized = _normalize_google_event(event, fallback_timezone)
        if normalized:
            events.append(normalized)
    return events


def _get_freebusy_for_email(organizer_service, email, time_min, time_max, fallback_timezone):
    """Query another user's busy times via FreeBusy using the organizer's credentials."""
    if not organizer_service or not time_min or not time_max:
        return []
    try:
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": email}],
        }
        result = organizer_service.freebusy().query(body=body).execute()
        busy_blocks = result.get("calendars", {}).get(email, {}).get("busy", [])
        events = []
        for block in busy_blocks:
            events.append({
                "start": block["start"],
                "end": block["end"],
                "timezone": fallback_timezone,
                "title": "Busy",
                "description": "",
            })
        return events
    except Exception as e:
        print(f"[freebusy] error querying {email}: {e}")
        return []


def _schedule_meeting(
    participants_payload,
    window_start,
    window_end,
    duration_minutes,
    location_type="virtual",
):
    """
    Placeholder scheduling function.
    Accepts participant JSON in a shape similar to the requested format.
    Returns start/end datetimes for the confirmed meeting.
    """
    try:
        from scheduler import create_meeting_from_payload

        org_settings_path = os.path.join(os.path.dirname(__file__), "org_settings.json")
        print(
            "[scheduler] window_start="
            f"{_format_log_time(window_start)}, "
            "window_end="
            f"{_format_log_time(window_end)}, "
            f"duration={duration_minutes}min, location={location_type}"
        )
        print(f"[scheduler] participants: {len(participants_payload)}")
        result = create_meeting_from_payload(
            people_payload=participants_payload,
            window_start=window_start,
            window_end=window_end,
            duration_minutes=duration_minutes,
            location_type=location_type,
            org_settings_path=org_settings_path,
            top_k=1,
        )
        if result:
            start_time, end_time, scored = result
            print(
                "[scheduler] SUCCESS: start="
                f"{_format_log_time(start_time)}, "
                "end="
                f"{_format_log_time(end_time)}, "
                f"score={scored[0].score if scored else 'N/A'}"
            )
            return start_time, end_time
        print("[scheduler] returned None — no valid slots found")
    except Exception as e:
        print(f"[scheduler] ERROR: {e}")
        import traceback
        traceback.print_exc()

    return None, None

# Initialize database tables on startup
with app.app_context():
    init_db()


@app.route("/")
def index():
    token = get_auth_token()
    if token:
        user = get_session(token)
        if user:
            return render_template("home.html", email=user["email"], events=[])
    return render_template("login.html")


# --- JSON API routes for React frontend ---


@app.route("/api/me")
def api_me():
    token = get_auth_token()
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user = get_session(token)
    if not user:
        return jsonify({"error": "session expired"}), 401
    return jsonify({"email": user["email"]})


@app.route("/api/events")
def api_events():
    token = get_auth_token()
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "session expired"}), 401

    db = SessionLocal()
    try:
        # Get meetings the user organized that are NOT yet synced to Google Calendar
        organized = db.query(ConfirmedMeeting).filter(
            ConfirmedMeeting.organizer_id == user_data["user_id"],
            ConfirmedMeeting.calendar_synced == False,
        ).all()

        # Keep only meetings where not all invitees have accepted
        pending = []
        for m in organized:
            if m.invites and not all(inv.status == "accepted" for inv in m.invites):
                pending.append(m)

        # Get meetings the user was invited to that are NOT yet synced
        invited = db.query(ConfirmedMeeting).join(
            ConfirmedMeetingInvite,
            ConfirmedMeetingInvite.confirmed_meeting_id == ConfirmedMeeting.id,
        ).filter(
            ConfirmedMeetingInvite.user_id == user_data["user_id"],
            ConfirmedMeeting.calendar_synced == False,
        ).all()

        # Combine and deduplicate
        all_meetings = {m.id: m for m in pending}
        for m in invited:
            all_meetings[m.id] = m
        result = sorted(all_meetings.values(), key=lambda m: m.start_time)

        return jsonify([m.to_dict() for m in result])
    finally:
        db.close()


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def api_events_delete(event_id):
    token = get_auth_token()
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "session expired"}), 401

    db = SessionLocal()
    try:
        meeting = db.query(ConfirmedMeeting).filter(
            ConfirmedMeeting.id == event_id,
        ).first()
        if not meeting:
            return jsonify({"error": "meeting not found"}), 404
        if meeting.organizer_id != user_data["user_id"]:
            return jsonify({"error": "only the organizer can delete this meeting"}), 403

        # Also delete the parent proposal (cascades to invites)
        proposal = meeting.proposal
        if proposal:
            db.delete(proposal)
        else:
            db.delete(meeting)
        db.commit()
        return jsonify({"message": "meeting deleted"})
    finally:
        db.close()


@app.route("/api/contacts/search")
def api_contacts_search():
    token = get_auth_token()
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    query = request.args.get("q", "")
    if not query:
        return jsonify([])
    service = get_people_service(token)
    if not service:
        return jsonify({"error": "no people service"}), 500
    result = service.people().searchDirectoryPeople(
        query=query,
        readMask="names,emailAddresses",
        sources=["DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE"],
        pageSize=10,
    ).execute()
    contacts = []
    for person in result.get("people", []):
        names = person.get("names", [])
        emails = person.get("emailAddresses", [])
        if emails:
            email_val = emails[0]["value"]
            if email_val.endswith("@columbia.edu"):
                contacts.append({
                    "name": names[0]["displayName"] if names else "",
                    "email": email_val,
                })
    return jsonify(contacts)


@app.route("/api/events/create", methods=["POST"])
def api_events_create():
    token = get_auth_token()
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "session expired"}), 401

    data = request.get_json()
    duration_minutes = int(data.get("durationMinutes", 60))
    location_type = data.get("locationType", "virtual")
    attendee_emails = data.get("attendees", [])
    summary = data.get("summary", "Meeting")
    description = data.get("description")
    urgency = data.get("urgency", "normal")
    location = data.get("location")

    # Parse the scheduling window
    window_start = _parse_datetime(data.get("start"), "start")
    window_end = _parse_datetime(data.get("end"), "end")
    if not window_start or not window_end:
        return jsonify({"error": "start and end are required"}), 400

    # Ensure datetimes are timezone-aware
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)

    # Build participant payloads with calendar data
    time_min = window_start.isoformat()
    time_max = window_end.isoformat()
    participants_payload = []

    db = SessionLocal()
    try:
        organizer_service = get_calendar_service(get_auth_token())
        organizer_email = user_data.get("email")
        organizer_name = user_data.get("name") or ""
        organizer_events = _get_freebusy_for_email(
            organizer_service, organizer_email, time_min, time_max, DEFAULT_TIMEZONE
        )
        print(f"[events] organizer {organizer_email}: FreeBusy returned {len(organizer_events)} busy blocks")
        for ev in organizer_events:
            print(
                "  - Busy "
                f"{_format_log_time(ev.get('start'))} → {_format_log_time(ev.get('end'))}"
            )
        participants_payload.append({
            "id": f"user_{user_data['user_id']}",
            "name": organizer_name,
            "email": organizer_email,
            "timezone": DEFAULT_TIMEZONE,
            "events": organizer_events,
        })

        # Add each attendee's calendar
        invited_users = []
        for email in attendee_emails:
            freebusy_events = _get_freebusy_for_email(
                organizer_service, email, time_min, time_max, DEFAULT_TIMEZONE
            )
            print(f"[events] attendee {email}: FreeBusy returned {len(freebusy_events)} busy blocks")
            for ev in freebusy_events:
                print(
                    "  - Busy "
                    f"{_format_log_time(ev.get('start'))} → {_format_log_time(ev.get('end'))}"
                )
            participants_payload.append({
                "id": email,
                "name": "",
                "email": email,
                "timezone": DEFAULT_TIMEZONE,
                "events": freebusy_events,
            })

            user = db.query(User).filter(User.email == email).first()
            if user:
                invited_users.append(user)

        # Run the scheduler to find the optimal meeting time
        start_time, end_time = _schedule_meeting(
            participants_payload,
            window_start,
            window_end,
            duration_minutes,
            location_type=location_type,
        )

        if not start_time or not end_time:
            return jsonify({
                "error": "no_valid_slots",
                "message": "No valid slots found for the requested window.",
            }), 409

        # Create proposal
        proposal = MeetingProposal(
            organizer_id=user_data["user_id"],
            title=summary,
            description=description,
            duration_minutes=duration_minutes,
            urgency=urgency,
            location=location,
            window_start=window_start,
            window_end=window_end,
            status="confirmed",
        )
        db.add(proposal)
        db.flush()

        # Create invites for attendees in our system
        for user in invited_users:
            db.add(MeetingInvite(
                proposal_id=proposal.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            ))

        # Create confirmed meeting with scheduler-determined times
        confirmed = ConfirmedMeeting(
            proposal_id=proposal.id,
            organizer_id=user_data["user_id"],
            title=summary,
            description=description,
            duration_minutes=duration_minutes,
            urgency=urgency,
            location=location,
            start_time=start_time,
            end_time=end_time,
            final_location=location,
            status="scheduled",
        )
        db.add(confirmed)
        db.flush()

        # Create confirmed invites
        for user in invited_users:
            db.add(ConfirmedMeetingInvite(
                confirmed_meeting_id=confirmed.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            ))

        db.flush()

        # Create notifications for all invitees (NOT the organizer)
        for user in invited_users:
            organizer_display = organizer_name or organizer_email or "Someone"
            meeting_time = confirmed.start_time.strftime('%B %d, %Y at %I:%M %p')
            notification = Notification(
                user_id=user.id,
                confirmed_meeting_id=confirmed.id,
                type="meeting_confirmed",
                title="Meeting invitation from " + organizer_display,
                message="You're invited to '" + confirmed.title + "' on " + meeting_time,
            )
            db.add(notification)

        db.commit()
        db.refresh(confirmed)

        return jsonify({"id": confirmed.id, "confirmed_meeting": confirmed.to_dict()}), 201
    finally:
        db.close()


# --- AI Scheduling ---


@app.route("/api/events/ai-create", methods=["POST"])
def api_events_ai_create():
    """
    AI-powered meeting creation.
    Accepts { "prompt": "lunch with john smith" } and uses Gemini to parse,
    resolve contacts, find availability, and pick the best slot.
    """
    token = get_auth_token()
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "session expired"}), 401

    data = request.get_json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    # Step 1: Parse the natural language prompt with Gemini
    from ai_scheduler import parse_meeting_request, select_best_slot

    try:
        parsed = parse_meeting_request(prompt, user_data.get("email", ""))
    except Exception as e:
        print(f"[ai-schedule] Gemini parse error: {e}")
        return jsonify({"error": "Failed to understand your request. Try being more specific."}), 400

    print(f"[ai-schedule] Parsed: {json.dumps(parsed, indent=2)}")

    attendee_names = parsed.get("attendee_names", [])
    if not attendee_names:
        return jsonify({"error": "No attendees found in your request. Try mentioning who you want to meet with."}), 400

    # Step 2: Resolve attendee names to emails via Google Directory
    people_service = get_people_service(token)
    if not people_service:
        return jsonify({"error": "no people service"}), 500

    resolved_emails = []
    resolution_log = []
    for name in attendee_names:
        try:
            result = people_service.people().searchDirectoryPeople(
                query=name,
                readMask="names,emailAddresses",
                sources=["DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE"],
                pageSize=3,
            ).execute()

            found = False
            for person in result.get("people", []):
                emails = person.get("emailAddresses", [])
                if emails:
                    email_val = emails[0]["value"]
                    if email_val.endswith("@columbia.edu") and email_val != user_data.get("email"):
                        names_list = person.get("names", [])
                        display_name = names_list[0]["displayName"] if names_list else email_val
                        resolved_emails.append(email_val)
                        resolution_log.append(f"{name} -> {display_name} ({email_val})")
                        found = True
                        break
            if not found:
                resolution_log.append(f"{name} -> NOT FOUND")
        except Exception as e:
            print(f"[ai-schedule] Directory search error for '{name}': {e}")
            resolution_log.append(f"{name} -> ERROR: {e}")

    print(f"[ai-schedule] Contact resolution: {resolution_log}")

    if not resolved_emails:
        return jsonify({
            "error": f"Could not find contacts for: {', '.join(attendee_names)}. Make sure they have a Columbia email.",
        }), 400

    # Step 3: Compute scheduling window
    now = datetime.now(timezone.utc)
    window_days = parsed.get("window_days", 7)
    window_start = now
    window_end = now + timedelta(days=window_days)

    # Step 4: Get FreeBusy data for all participants
    time_min = window_start.isoformat()
    time_max = window_end.isoformat()
    participants_payload = []

    organizer_service = get_calendar_service(token)
    organizer_email = user_data.get("email")
    organizer_name = user_data.get("name") or ""

    organizer_events = _get_freebusy_for_email(
        organizer_service, organizer_email, time_min, time_max, DEFAULT_TIMEZONE
    )
    participants_payload.append({
        "id": f"user_{user_data['user_id']}",
        "name": organizer_name,
        "email": organizer_email,
        "timezone": DEFAULT_TIMEZONE,
        "events": organizer_events,
    })

    db = SessionLocal()
    try:
        invited_users = []
        for email in resolved_emails:
            freebusy_events = _get_freebusy_for_email(
                organizer_service, email, time_min, time_max, DEFAULT_TIMEZONE
            )
            participants_payload.append({
                "id": email,
                "name": "",
                "email": email,
                "timezone": DEFAULT_TIMEZONE,
                "events": freebusy_events,
            })
            user = db.query(User).filter(User.email == email).first()
            if user:
                invited_users.append(user)

        # Step 5: Run the scheduler to get top-5 candidate slots
        duration_minutes = parsed.get("duration_minutes", 60)
        location_type = parsed.get("location_type", "virtual")

        from scheduler import create_meeting_from_payload
        org_settings_path = os.path.join(os.path.dirname(__file__), "org_settings.json")

        result = create_meeting_from_payload(
            people_payload=participants_payload,
            window_start=window_start,
            window_end=window_end,
            duration_minutes=duration_minutes,
            location_type=location_type,
            org_settings_path=org_settings_path,
            top_k=5,
        )

        if not result:
            return jsonify({
                "error": "no_valid_slots",
                "message": "No available time slots found. Try a wider time window.",
            }), 409

        start_time, end_time, scored = result

        # Step 6: Let Gemini pick the best slot considering context
        slots_for_ai = []
        from scheduler import _start_of_week
        reference_start = _start_of_week(window_start, tz_str=DEFAULT_TIMEZONE)

        for s in scored:
            s_start = reference_start + timedelta(minutes=s.start)
            s_end = reference_start + timedelta(minutes=s.end)
            slots_for_ai.append({
                "start_time": s_start.isoformat(),
                "end_time": s_end.isoformat(),
                "score": s.score,
            })

        try:
            best_index = select_best_slot(slots_for_ai, prompt, parsed)
        except Exception as e:
            print(f"[ai-schedule] Gemini select error: {e}, falling back to top scorer")
            best_index = 0

        best_slot = slots_for_ai[best_index]
        start_time = datetime.fromisoformat(best_slot["start_time"])
        end_time = datetime.fromisoformat(best_slot["end_time"])

        print(f"[ai-schedule] Gemini picked slot {best_index + 1}/{len(slots_for_ai)}: "
              f"{_format_log_time(start_time)} -> {_format_log_time(end_time)}")

        # Step 7: Create the meeting (reuse existing DB logic)
        summary = parsed.get("title", "Meeting")
        description = f"Scheduled by AI: \"{prompt}\""
        urgency = parsed.get("urgency", "normal")
        location = parsed.get("location") or (
            "In person" if location_type == "in-person" else "Online"
        )

        proposal = MeetingProposal(
            organizer_id=user_data["user_id"],
            title=summary,
            description=description,
            duration_minutes=duration_minutes,
            urgency=urgency,
            location=location,
            window_start=window_start,
            window_end=window_end,
            status="confirmed",
        )
        db.add(proposal)
        db.flush()

        for user in invited_users:
            db.add(MeetingInvite(
                proposal_id=proposal.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            ))

        confirmed = ConfirmedMeeting(
            proposal_id=proposal.id,
            organizer_id=user_data["user_id"],
            title=summary,
            description=description,
            duration_minutes=duration_minutes,
            urgency=urgency,
            location=location,
            start_time=start_time,
            end_time=end_time,
            final_location=location,
            status="scheduled",
        )
        db.add(confirmed)
        db.flush()

        for user in invited_users:
            db.add(ConfirmedMeetingInvite(
                confirmed_meeting_id=confirmed.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            ))

        db.flush()

        for user in invited_users:
            organizer_display = organizer_name or organizer_email or "Someone"
            meeting_time = confirmed.start_time.strftime('%B %d, %Y at %I:%M %p')
            notification = Notification(
                user_id=user.id,
                confirmed_meeting_id=confirmed.id,
                type="meeting_confirmed",
                title="Meeting invitation from " + organizer_display,
                message="You're invited to '" + confirmed.title + "' on " + meeting_time,
            )
            db.add(notification)

        db.commit()
        db.refresh(confirmed)

        return jsonify({
            "id": confirmed.id,
            "confirmed_meeting": confirmed.to_dict(),
            "ai_parsed": parsed,
            "resolved_contacts": resolution_log,
        }), 201
    finally:
        db.close()


# --- Auth routes ---


@app.route("/auth/login")
def auth_login():
    auth_url, state = get_authorization_url()
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    state = session.get("oauth_state")
    session_token, email = handle_callback(request.url, state)
    session["session_token"] = session_token
    return redirect("http://localhost:5173")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("http://localhost:5173")


@app.route("/auth/extension/token", methods=["POST"])
def auth_extension_token():
    """
    Token exchange endpoint for Chrome extension.
    Receives authorization code from extension's launchWebAuthFlow,
    exchanges it for tokens, creates user/session, returns session token.
    """
    import requests
    import secrets

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    code = data.get("code")
    redirect_uri = data.get("redirectUri")

    if not code or not redirect_uri:
        return jsonify({"error": "code and redirectUri required"}), 400

    # Load client credentials
    import json
    client_secret_path = os.path.join(os.path.dirname(__file__), "client_secret.json")
    with open(client_secret_path) as f:
        client_config = json.load(f)["web"]

    # Exchange code for tokens
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_config["client_id"],
            "client_secret": client_config["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    if not token_response.ok:
        return jsonify({"error": "token exchange failed", "details": token_response.text}), 400

    tokens = token_response.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    # Get user info
    userinfo_response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if not userinfo_response.ok:
        return jsonify({"error": "failed to get user info"}), 400

    user_info = userinfo_response.json()
    email = user_info.get("email")
    name = user_info.get("name", "")

    if not email:
        return jsonify({"error": "no email in user info"}), 400

    # Create or update user and session
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name)
            db.add(user)

        user.google_access_token = access_token
        user.google_refresh_token = refresh_token
        user.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(user)

        # Create session
        from db import Session as DbSession
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        db_session = DbSession(
            session_token=session_token,
            user_id=user.id,
            expires_at=expires_at,
        )
        db.add(db_session)
        db.commit()

        return jsonify({
            "session_token": session_token,
            "email": email,
            "name": name,
        })
    finally:
        db.close()


# ============ API ENDPOINTS ============

@app.route("/api/users/lookup", methods=["GET"])
def api_lookup_user():
    """Look up a user by email."""
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "email parameter required"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "user not found"}), 404

    return jsonify(user)


@app.route("/api/users/search", methods=["GET"])
def api_search_users():
    """Search for users by email (partial match)."""
    query = request.args.get("q", "")
    if len(query) < 2:
        return jsonify({"error": "query must be at least 2 characters"}), 400

    db = SessionLocal()
    try:
        search_pattern = "%" + query + "%"
        users = db.query(User).filter(User.email.ilike(search_pattern)).limit(10).all()
        return jsonify([u.to_dict() for u in users])
    finally:
        db.close()


@app.route("/api/calendar/availability", methods=["POST"])
def api_get_availability():
    """
    Get calendar availability for multiple users.

    Request body:
    {
        "user_emails": ["user1@example.com", "user2@example.com"],
        "time_min": "2024-01-01T00:00:00Z",
        "time_max": "2024-01-07T23:59:59Z"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_emails = data.get("user_emails", [])
    time_min = data.get("time_min")
    time_max = data.get("time_max")

    if not user_emails:
        return jsonify({"error": "user_emails required"}), 400
    if not time_min or not time_max:
        return jsonify({"error": "time_min and time_max required"}), 400

    db = SessionLocal()
    try:
        results = {}
        for email in user_emails:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                results[email] = {"error": "user not found"}
                continue

            service = get_calendar_service_for_user(user.id)
            if not service:
                results[email] = {"error": "no calendar access"}
                continue

            try:
                events_result = service.events().list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                events = events_result.get("items", [])
                busy_blocks = []
                for event in events:
                    start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
                    end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
                    busy_blocks.append({
                        "start": start,
                        "end": end,
                        "summary": event.get("summary", "Busy"),
                    })

                results[email] = {"busy_blocks": busy_blocks}
            except Exception as e:
                results[email] = {"error": str(e)}

        return jsonify(results)
    finally:
        db.close()


# ============ MEETING ENDPOINTS ============

@app.route("/api/meetings", methods=["POST"])
def api_create_meeting():
    """
    Create a new meeting request.

    Request body:
    {
        "title": "Team Standup",
        "description": "Daily sync",
        "duration_minutes": 30,
        "urgency": "normal",  // low, normal, high, urgent
        "location": "Conference Room A",
        "window_start": "2024-01-01T09:00:00Z",
        "window_end": "2024-01-05T17:00:00Z",
        "invited_emails": ["alice@example.com", "bob@example.com"]
    }
    """
    # Check if user is logged in
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    # Validate required fields
    title = data.get("title")
    duration_minutes = data.get("duration_minutes")
    invited_emails = data.get("invited_emails", [])
    timezone_name = data.get("timezone", DEFAULT_TIMEZONE)
    location_type = data.get("location_type", "virtual")
    participant_events = data.get("participant_events")  # optional: {email: [events]}

    if not title:
        return jsonify({"error": "title required"}), 400
    if not duration_minutes:
        return jsonify({"error": "duration_minutes required"}), 400
    if not invited_emails:
        return jsonify({"error": "invited_emails required"}), 400
    if participant_events is not None and not isinstance(participant_events, dict):
        return jsonify({"error": "participant_events must be an object keyed by email"}), 400
    try:
        duration_minutes = int(duration_minutes)
    except (TypeError, ValueError):
        return jsonify({"error": "duration_minutes must be an integer"}), 400

    try:
        window_start = _parse_datetime(data.get("window_start"), "window_start")
        window_end = _parse_datetime(data.get("window_end"), "window_end")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    db = SessionLocal()
    try:
        # Create the meeting proposal
        proposal = MeetingProposal(
            organizer_id=user_data["user_id"],
            title=title,
            description=data.get("description"),
            duration_minutes=duration_minutes,
            urgency=data.get("urgency", "normal"),
            location=data.get("location"),
            window_start=window_start,
            window_end=window_end,
            status="pending",
        )
        db.add(proposal)
        db.flush()  # Get the proposal ID

        participants_payload = []
        organizer_service = get_calendar_service(get_auth_token())
        organizer_email = user_data.get("email")
        organizer_name = user_data.get("name") or ""
        if participant_events is None:
            organizer_events = _get_freebusy_for_email(
                organizer_service,
                organizer_email,
                window_start.isoformat() if window_start else None,
                window_end.isoformat() if window_end else None,
                timezone_name,
            )
        else:
            organizer_events = participant_events.get(organizer_email) or []
        participants_payload.append({
            "id": f"user_{user_data['user_id']}",
            "name": organizer_name,
            "email": organizer_email,
            "timezone": timezone_name,
            "events": organizer_events,
        })

        # Create invites for each invited user
        not_found = []
        invited_users = []
        for email in invited_emails:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                not_found.append(email)
            else:
                invited_users.append(user)
                invite = MeetingInvite(
                    proposal_id=proposal.id,
                    user_id=user.id,
                    is_required=True,
                    status="pending",
                )
                db.add(invite)

        for user in invited_users:
            if participant_events is None:
                user_events = _get_freebusy_for_email(
                    organizer_service,
                    user.email,
                    window_start.isoformat() if window_start else None,
                    window_end.isoformat() if window_end else None,
                    timezone_name,
                )
            else:
                user_events = participant_events.get(user.email) or []
            participants_payload.append({
                "id": user.email,
                "name": user.name or "",
                "email": user.email,
                "timezone": timezone_name,
                "events": user_events,
            })

        print("Scheduler payload:")
        print(json.dumps(participants_payload, indent=2))

        # Call scheduling function to create confirmed meeting
        start_time, end_time = _schedule_meeting(
            participants_payload,
            window_start,
            window_end,
            duration_minutes,
            location_type=location_type,
        )

        if not start_time or not end_time:
            proposal.status = "pending"
            db.commit()
            return jsonify({
                "error": "no_valid_slots",
                "message": "No valid slots found for the requested window.",
                "proposal": proposal.to_dict(),
            }), 409

        confirmed_meeting = ConfirmedMeeting(
            proposal_id=proposal.id,
            organizer_id=proposal.organizer_id,
            title=proposal.title,
            description=proposal.description,
            duration_minutes=proposal.duration_minutes,
            urgency=proposal.urgency,
            location=proposal.location,
            start_time=start_time,
            end_time=end_time,
            final_location=proposal.location,
            status="scheduled",
        )
        db.add(confirmed_meeting)
        db.flush()

        for user in invited_users:
            confirmed_invite = ConfirmedMeetingInvite(
                confirmed_meeting_id=confirmed_meeting.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            )
            db.add(confirmed_invite)

        proposal.status = "confirmed"

        db.flush()

        # Create notifications for all invitees (NOT the organizer)
        for user in invited_users:
            organizer_display = organizer_name or organizer_email or "Someone"
            meeting_time = confirmed_meeting.start_time.strftime('%B %d, %Y at %I:%M %p')
            notification = Notification(
                user_id=user.id,
                confirmed_meeting_id=confirmed_meeting.id,
                type="meeting_confirmed",
                title="Meeting invitation from " + organizer_display,
                message="You're invited to '" + confirmed_meeting.title + "' on " + meeting_time,
            )
            db.add(notification)

        db.commit()
        db.refresh(proposal)
        db.refresh(confirmed_meeting)

        response = {
            "proposal": proposal.to_dict(),
            "confirmed_meeting": confirmed_meeting.to_dict(),
            "message": "Meeting proposal created successfully",
        }
        if not_found:
            response["warning"] = "Users not found: " + str(not_found)

        return jsonify(response), 201
    finally:
        db.close()


@app.route("/api/meetings", methods=["GET"])
def api_get_my_meetings():
    """Get meeting proposals organized by the current user."""
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    db = SessionLocal()
    try:
        proposals = db.query(MeetingProposal).filter(
            MeetingProposal.organizer_id == user_data["user_id"]
        ).order_by(MeetingProposal.created_at.desc()).all()

        return jsonify([p.to_dict() for p in proposals])
    finally:
        db.close()


@app.route("/api/meetings/<int:meeting_id>", methods=["GET"])
def api_get_meeting(meeting_id):
    """Get a specific meeting proposal by ID."""
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    db = SessionLocal()
    try:
        proposal = db.query(MeetingProposal).filter(MeetingProposal.id == meeting_id).first()
        if not proposal:
            return jsonify({"error": "proposal not found"}), 404

        return jsonify(proposal.to_dict())
    finally:
        db.close()


@app.route("/api/meetings/<int:proposal_id>/confirm", methods=["POST"])
def api_confirm_proposal(proposal_id):
    """
    Confirm a meeting proposal with a scheduled time (called by algorithm).
    Creates a ConfirmedMeeting from the proposal.

    Request body:
    {
        "start_time": "2024-02-11T14:00:00Z",
        "end_time": "2024-02-11T14:30:00Z",
        "final_location": "Zoom"  // optional, defaults to proposal location
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    start_time = data.get("start_time")
    end_time = data.get("end_time")

    if not start_time or not end_time:
        return jsonify({"error": "start_time and end_time required"}), 400

    db = SessionLocal()
    try:
        proposal = db.query(MeetingProposal).filter(MeetingProposal.id == proposal_id).first()
        if not proposal:
            return jsonify({"error": "proposal not found"}), 404

        if proposal.status == "confirmed":
            return jsonify({"error": "proposal already confirmed"}), 400

        # Create confirmed meeting from proposal
        confirmed = ConfirmedMeeting(
            proposal_id=proposal.id,
            organizer_id=proposal.organizer_id,
            title=proposal.title,
            description=proposal.description,
            duration_minutes=proposal.duration_minutes,
            urgency=proposal.urgency,
            location=proposal.location,
            start_time=datetime.fromisoformat(start_time.replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(end_time.replace("Z", "+00:00")),
            final_location=data.get("final_location", proposal.location),
            status="scheduled",
        )
        db.add(confirmed)

        # Update proposal status
        proposal.status = "confirmed"
        proposal.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(confirmed)

        # Create notifications for all invitees (NOT the host/organizer)
        organizer_id = proposal.organizer_id
        for invite in proposal.invites:
            if invite.user_id != organizer_id:  # Skip the host
                organizer_display = proposal.organizer.name or proposal.organizer.email
                meeting_time = confirmed.start_time.strftime('%B %d, %Y at %I:%M %p')
                notification = Notification(
                    user_id=invite.user_id,
                    confirmed_meeting_id=confirmed.id,
                    type="meeting_confirmed",
                    title="Meeting invitation from " + organizer_display,
                    message="You're invited to '" + confirmed.title + "' on " + meeting_time,
                )
                db.add(notification)

        db.commit()
        db.refresh(proposal)

        return jsonify({
            "message": "Meeting confirmed successfully",
            "confirmed_meeting": confirmed.to_dict(),
            "proposal": proposal.to_dict(),
        })
    finally:
        db.close()


# ============ INVITE ENDPOINTS ============

@app.route("/api/invites", methods=["GET"])
def api_get_my_invites():
    """
    Get all meeting invites for the current user.
    This is what shows up when user opens the Chrome extension.
    """
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    status_filter = request.args.get("status")  # optional: pending, accepted, declined

    db = SessionLocal()
    try:
        query = db.query(MeetingInvite).filter(
            MeetingInvite.user_id == user_data["user_id"]
        )

        if status_filter:
            query = query.filter(MeetingInvite.status == status_filter)

        invites = query.order_by(MeetingInvite.invited_at.desc()).all()

        # Include meeting details with each invite
        result = []
        for invite in invites:
            invite_data = invite.to_dict()
            invite_data["proposal"] = invite.proposal.to_dict(include_invites=False)
            result.append(invite_data)

        return jsonify(result)
    finally:
        db.close()


@app.route("/api/invites/<int:invite_id>/respond", methods=["POST"])
def api_respond_to_invite(invite_id):
    """
    Accept or decline a meeting invite.

    Request body:
    {
        "response": "accepted"  // or "declined"
    }
    """
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    response = data.get("response")
    if response not in ["accepted", "declined"]:
        return jsonify({"error": "response must be 'accepted' or 'declined'"}), 400

    db = SessionLocal()
    try:
        invite = db.query(MeetingInvite).filter(
            MeetingInvite.id == invite_id,
            MeetingInvite.user_id == user_data["user_id"]
        ).first()

        if not invite:
            return jsonify({"error": "invite not found"}), 404

        invite.status = response
        invite.responded_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(invite)

        return jsonify({
            "message": "Invite " + response,
            "invite": invite.to_dict(),
        })
    finally:
        db.close()


# ============ CALENDAR SYNC ============

def _sync_meeting_to_calendars(confirmed_meeting, db):
    """
    Create a Google Calendar event on the organizer's calendar with all attendees.
    Google Calendar automatically adds the event to all attendees' calendars.
    Called once all invitees have accepted.
    """
    if confirmed_meeting.calendar_synced:
        print("[calendar] Already synced, skipping")
        return

    # Collect all participant emails
    organizer = db.query(User).filter(User.id == confirmed_meeting.organizer_id).first()
    attendee_emails = []
    if organizer:
        attendee_emails.append(organizer.email)
    for inv in confirmed_meeting.invites:
        user = db.query(User).filter(User.id == inv.user_id).first()
        if user and user.email not in attendee_emails:
            attendee_emails.append(user.email)

    print(f"[calendar] Syncing meeting '{confirmed_meeting.title}' with attendees: {attendee_emails}")

    event_body = {
        "summary": confirmed_meeting.title,
        "description": confirmed_meeting.description or "",
        "location": confirmed_meeting.final_location or confirmed_meeting.location or "",
        "start": {
            "dateTime": confirmed_meeting.start_time.isoformat(),
            "timeZone": "America/New_York",
        },
        "end": {
            "dateTime": confirmed_meeting.end_time.isoformat(),
            "timeZone": "America/New_York",
        },
        "attendees": [{"email": email} for email in attendee_emails],
    }

    print(f"[calendar] Event body: {event_body}")

    # Create once on organizer's calendar — Google adds it to all attendees
    try:
        service = get_calendar_service_for_user(confirmed_meeting.organizer_id)
        if service:
            service.events().insert(
                calendarId="primary",
                body=event_body,
                sendUpdates="none",
            ).execute()
            print(f"[calendar] Created event on organizer's calendar with {len(attendee_emails)} attendees")
            confirmed_meeting.calendar_synced = True
            db.commit()
        else:
            print(f"[calendar] No calendar service for organizer (user {confirmed_meeting.organizer_id}), skipping")
    except Exception as e:
        print(f"[calendar] Failed to create event: {e}")
        import traceback
        traceback.print_exc()


# ============ NOTIFICATION ENDPOINTS ============

@app.route("/api/notifications", methods=["GET"])
def api_get_notifications():
    """
    Get all notifications for the current user.
    Returns LinkedIn-style meeting confirmation notifications.
    """
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    db = SessionLocal()
    try:
        notifications = db.query(Notification).filter(
            Notification.user_id == user_data["user_id"]
        ).order_by(Notification.created_at.desc()).all()

        return jsonify([n.to_dict() for n in notifications])
    finally:
        db.close()


@app.route("/api/notifications/unread-count", methods=["GET"])
def api_get_unread_count():
    """Get count of unread notifications."""
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    db = SessionLocal()
    try:
        count = db.query(Notification).filter(
            Notification.user_id == user_data["user_id"],
            Notification.is_read == False
        ).count()

        return jsonify({"count": count})
    finally:
        db.close()


@app.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def api_mark_notification_read(notification_id):
    """Mark a notification as read."""
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_data["user_id"]
        ).first()

        if not notification:
            return jsonify({"error": "notification not found"}), 404

        notification.is_read = True
        db.commit()

        return jsonify({"message": "Notification marked as read"})
    finally:
        db.close()


@app.route("/api/notifications/<int:notification_id>/respond", methods=["POST"])
def api_respond_to_notification(notification_id):
    """
    Respond to a meeting notification (accept/decline).

    Request body:
    {
        "response": "accepted"  // or "declined"
    }
    """
    token = get_auth_token()
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    response = data.get("response")
    if response not in ["accepted", "declined"]:
        return jsonify({"error": "response must be 'accepted' or 'declined'"}), 400

    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_data["user_id"]
        ).first()

        if not notification:
            return jsonify({"error": "notification not found"}), 404

        notification.response = response
        notification.responded_at = datetime.now(timezone.utc)
        notification.is_read = True

        # Keep ConfirmedMeetingInvite in sync with the notification response
        confirmed_invite = db.query(ConfirmedMeetingInvite).filter(
            ConfirmedMeetingInvite.confirmed_meeting_id == notification.confirmed_meeting_id,
            ConfirmedMeetingInvite.user_id == user_data["user_id"],
        ).first()
        if confirmed_invite:
            confirmed_invite.status = response
            confirmed_invite.responded_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(notification)

        # If all invitees accepted, sync to everyone's Google Calendar
        calendar_synced = False
        if response == "accepted":
            meeting = notification.confirmed_meeting
            all_notifications = db.query(Notification).filter(
                Notification.confirmed_meeting_id == meeting.id,
            ).all()
            responses = {n.user_id: n.response for n in all_notifications}
            all_accepted = all(r == "accepted" for r in responses.values())
            print(f"[calendar-sync] Meeting {meeting.id}: notification responses = {responses}")
            print(f"[calendar-sync] all_accepted={all_accepted}, calendar_synced={meeting.calendar_synced}")
            if all_accepted and not meeting.calendar_synced:
                print(f"[calendar-sync] Triggering calendar sync for meeting {meeting.id}")
                _sync_meeting_to_calendars(meeting, db)
                calendar_synced = True

        return jsonify({
            "message": "Meeting " + response,
            "notification": notification.to_dict(),
            "calendar_synced": calendar_synced,
        })
    finally:
        db.close()


@app.route("/api/notifications/clear-responded", methods=["DELETE"])
def api_clear_responded_notifications():
    """Delete all notifications that the user has already responded to."""
    token = session.get("session_token")
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "unauthorized"}), 401

    db = SessionLocal()
    try:
        deleted = db.query(Notification).filter(
            Notification.user_id == user_data["user_id"],
            Notification.response.isnot(None),
        ).delete(synchronize_session="fetch")
        db.commit()
        return jsonify({"deleted": deleted})
    finally:
        db.close()


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow HTTP for local dev
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # Allow Google to return extra scopes
    app.run(debug=True, port=8080)
