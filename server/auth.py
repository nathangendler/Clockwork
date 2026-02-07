import os
import secrets
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# In-memory session store
sessions = {}

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

    # Get user email
    people_service = build("oauth2", "v2", credentials=credentials)
    user_info = people_service.userinfo().get().execute()
    email = user_info["email"]

    # Create session token
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {
        "email": email,
        "credentials": credentials,
    }

    return session_token, email


def get_session(session_token):
    return sessions.get(session_token)


def get_calendar_service(session_token):
    sess = get_session(session_token)
    if not sess:
        return None
    return build("calendar", "v3", credentials=sess["credentials"])


def get_people_service(session_token):
    sess = get_session(session_token)
    if not sess:
        return None
    return build("people", "v1", credentials=sess["credentials"])
