from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, redirect, request, session, render_template, jsonify
from flask_cors import CORS

from auth import (
    get_authorization_url,
    handle_callback,
    get_session,
    get_calendar_service,
    get_people_service,
    get_user_by_email,
    get_calendar_service_for_user,
)
from db import init_db, SessionLocal, User, MeetingProposal, ConfirmedMeeting, MeetingInvite, ConfirmedMeetingInvite

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}}, supports_credentials=True)

# ===== Scheduling helpers =====

DEFAULT_TIMEZONE = "America/New_York"


def _parse_datetime(value, field_name):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def _schedule_meeting(participants_payload, window_start, window_end, duration_minutes):
    """
    Placeholder scheduling function.
    Accepts participant JSON in a shape similar to the requested format.
    Returns start/end datetimes for the confirmed meeting.
    """
    duration = timedelta(minutes=duration_minutes)
    start_time = window_start or (datetime.now(timezone.utc) + timedelta(hours=1))
    end_time = start_time + duration
    if window_end and end_time > window_end:
        end_time = window_end
        start_time = end_time - duration
    return start_time, end_time

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
    service = get_calendar_service(token)
    if not service:
        return jsonify({"error": "no calendar service"}), 500
    now = datetime.now(timezone.utc).isoformat()
    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return jsonify(result.get("items", []))


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
    service = get_calendar_service(token)
    if not service:
        return jsonify({"error": "no calendar service"}), 500
    data = request.get_json()
    event = {
        "summary": data.get("summary", "Meeting"),
        "start": {"dateTime": data["start"], "timeZone": "America/New_York"},
        "end": {"dateTime": data["end"], "timeZone": "America/New_York"},
        "attendees": [{"email": e} for e in data.get("attendees", [])],
    }
    created = service.events().insert(
        calendarId="primary",
        body=event,
        sendUpdates="all",
    ).execute()
    return jsonify({"id": created["id"], "htmlLink": created.get("htmlLink")})


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
        users = db.query(User).filter(User.email.ilike(f"%{query}%")).limit(10).all()
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
    participant_events = data.get("participant_events") or {}  # optional: {email: [events]}

    if not title:
        return jsonify({"error": "title required"}), 400
    if not duration_minutes:
        return jsonify({"error": "duration_minutes required"}), 400
    if not invited_emails:
        return jsonify({"error": "invited_emails required"}), 400
    if not isinstance(participant_events, dict):
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

        organizer = db.query(User).filter(User.id == user_data["user_id"]).first()
        participants_payload = []
        if organizer:
            participants_payload.append(
                _build_participant_payload(
                    organizer,
                    timezone_name,
                    participant_events.get(organizer.email),
                )
            )

        # Create invites for each invited user
        not_found = []
        invited_users = []
        for email in invited_emails:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                not_found.append(email)
                continue
            invited_users.append(user)

            invite = MeetingInvite(
                proposal_id=proposal.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            )
            db.add(invite)

        for user in invited_users:
            participants_payload.append(
                _build_participant_payload(
                    user,
                    timezone_name,
                    participant_events.get(user.email),
                )
            )

        # Call scheduling function to create confirmed meeting
        start_time, end_time = _schedule_meeting(
            participants_payload,
            window_start,
            window_end,
            duration_minutes,
        )

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

        db.commit()
        db.refresh(proposal)
        db.refresh(confirmed_meeting)

        response = {
            "proposal": proposal.to_dict(),
            "confirmed_meeting": confirmed_meeting.to_dict(),
            "message": "Meeting proposal created successfully",
        }
        if not_found:
            response["warning"] = f"Users not found: {not_found}"

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
            "message": f"Invite {response}",
            "invite": invite.to_dict(),
        })
    finally:
        db.close()


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow HTTP for local dev
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # Allow Google to return extra scopes
    app.run(debug=True, port=8080)
