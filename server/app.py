from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
import json
from zoneinfo import ZoneInfo

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
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}}, supports_credentials=True)

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
    token = session.get("session_token")
    if token:
        user = get_session(token)
        if user:
            return render_template("home.html", email=user["email"], events=[])
    return render_template("login.html")


# --- JSON API routes for React frontend ---


@app.route("/api/me")
def api_me():
    token = session.get("session_token")
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user = get_session(token)
    if not user:
        return jsonify({"error": "session expired"}), 401
    return jsonify({"email": user["email"]})


@app.route("/api/events")
def api_events():
    token = session.get("session_token")
    if not token:
        return jsonify({"error": "not authenticated"}), 401
    user_data = get_session(token)
    if not user_data:
        return jsonify({"error": "session expired"}), 401

    db = SessionLocal()
    try:
        # Get all meetings the user organized or was invited to
        organized = db.query(ConfirmedMeeting).filter(
            ConfirmedMeeting.organizer_id == user_data["user_id"],
        ).all()

        invited = db.query(ConfirmedMeeting).join(
            ConfirmedMeetingInvite,
            ConfirmedMeetingInvite.confirmed_meeting_id == ConfirmedMeeting.id,
        ).filter(
            ConfirmedMeetingInvite.user_id == user_data["user_id"],
        ).all()

        # Deduplicate and sort
        seen = set()
        meetings = []
        for m in organized + invited:
            if m.id not in seen:
                seen.add(m.id)
                meetings.append(m)
        meetings.sort(key=lambda m: m.start_time)

        return jsonify([m.to_dict() for m in meetings])
    finally:
        db.close()


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def api_events_delete(event_id):
    token = session.get("session_token")
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
    token = session.get("session_token")
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
    token = session.get("session_token")
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
        organizer_service = get_calendar_service(session.get("session_token"))
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
            organizer_display = organizer.name or organizer.email if organizer else "Someone"
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
    token = session.get("session_token")
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
        organizer_service = get_calendar_service(session.get("session_token"))
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
            organizer_display = organizer.name or organizer.email if organizer else "Someone"
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
    token = session.get("session_token")
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
    token = session.get("session_token")
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
    token = session.get("session_token")
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
    token = session.get("session_token")
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


# ============ NOTIFICATION ENDPOINTS ============

@app.route("/api/notifications", methods=["GET"])
def api_get_notifications():
    """
    Get all notifications for the current user.
    Returns LinkedIn-style meeting confirmation notifications.
    """
    token = session.get("session_token")
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
    token = session.get("session_token")
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
    token = session.get("session_token")
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
    token = session.get("session_token")
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
        db.commit()
        db.refresh(notification)

        return jsonify({
            "message": "Meeting " + response,
            "notification": notification.to_dict(),
        })
    finally:
        db.close()


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow HTTP for local dev
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # Allow Google to return extra scopes
    app.run(debug=True, port=8080)
