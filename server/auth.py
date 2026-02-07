import os
import secrets
from datetime import datetime, timezone, timedelta
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from db import SessionLocal, User, Session

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/directory.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

CLIENT_SECRET_FILE = os.path.join(os.path.dirname(__file__), "client_secret.json")
REDIRECT_URI = "http://localhost:8080/auth/callback"


def create_flow():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    return flow


def get_authorization_url():
    flow = create_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def handle_callback(authorization_response, state):
    flow = create_flow()
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials

    # Get user info
    people_service = build("oauth2", "v2", credentials=credentials)
    user_info = people_service.userinfo().get().execute()
    email = user_info["email"]
    name = user_info.get("name", "")

    db = SessionLocal()
    try:
        # Find or create user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name)
            db.add(user)

        # Update tokens
        user.google_access_token = credentials.token
        user.google_refresh_token = credentials.refresh_token
        user.token_expiry = credentials.expiry
        user.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(user)

        # Create session
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        session = Session(
            session_token=session_token,
            user_id=user.id,
            expires_at=expires_at,
        )
        db.add(session)
        db.commit()

        return session_token, email
    finally:
        db.close()


def get_session(session_token):
    """Get user data from session token."""
    if not session_token:
        return None

    db = SessionLocal()
    try:
        session = db.query(Session).filter(
            Session.session_token == session_token
        ).first()

        if not session:
            return None

        # Check if session expired
        if session.expires_at and session.expires_at < datetime.now(timezone.utc):
            db.delete(session)
            db.commit()
            return None

        user = session.user
        if not user:
            return None

        return {
            "email": user.email,
            "name": user.name,
            "user_id": user.id,
        }
    finally:
        db.close()


def get_calendar_service(session_token):
    """Get Google Calendar service for a session."""
    if not session_token:
        return None

    db = SessionLocal()
    try:
        session = db.query(Session).filter(
            Session.session_token == session_token
        ).first()

        if not session or not session.user:
            return None

        user = session.user
        credentials = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=_get_client_id(),
            client_secret=_get_client_secret(),
            scopes=SCOPES,
        )

        return build("calendar", "v3", credentials=credentials)
    finally:
        db.close()


def get_people_service(session_token):
    """Get Google People service for a session."""
    if not session_token:
        return None

    db = SessionLocal()
    try:
        session = db.query(Session).filter(
            Session.session_token == session_token
        ).first()

        if not session or not session.user:
            return None

        user = session.user
        credentials = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=_get_client_id(),
            client_secret=_get_client_secret(),
            scopes=SCOPES,
        )

        return build("people", "v1", credentials=credentials)
    finally:
        db.close()


def get_user_by_email(email: str):
    """Look up a user by email."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return user.to_dict() if user else None
    finally:
        db.close()


def get_calendar_service_for_user(user_id: int):
    """Get Google Calendar service for a specific user by ID."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.google_access_token:
            return None

        credentials = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=_get_client_id(),
            client_secret=_get_client_secret(),
            scopes=SCOPES,
        )

        return build("calendar", "v3", credentials=credentials)
    finally:
        db.close()


def _get_client_id():
    """Get client ID from client_secret.json."""
    import json
    with open(CLIENT_SECRET_FILE) as f:
        data = json.load(f)
        return data.get("web", {}).get("client_id")


def _get_client_secret():
    """Get client secret from client_secret.json."""
    import json
    with open(CLIENT_SECRET_FILE) as f:
        data = json.load(f)
        return data.get("web", {}).get("client_secret")
