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
from db import init_db, SessionLocal, User, MeetingProposal, ConfirmedMeeting, MeetingInvite, Notification

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}}, supports_credentials=True)

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

    if not title:
        return jsonify({"error": "title required"}), 400
    if not duration_minutes:
        return jsonify({"error": "duration_minutes required"}), 400
    if not invited_emails:
        return jsonify({"error": "invited_emails required"}), 400

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
            window_start=data.get("window_start"),
            window_end=data.get("window_end"),
            status="pending",
        )
        db.add(proposal)
        db.flush()  # Get the proposal ID

        # Create invites for each invited user
        not_found = []
        for email in invited_emails:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                not_found.append(email)
                continue

            invite = MeetingInvite(
                proposal_id=proposal.id,
                user_id=user.id,
                is_required=True,
                status="pending",
            )
            db.add(invite)

        db.commit()
        db.refresh(proposal)

        response = {
            "proposal": proposal.to_dict(),
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
