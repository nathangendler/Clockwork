import os
from flask import Flask, redirect, request, session, render_template, url_for
from dotenv import load_dotenv

from auth import get_authorization_url, handle_callback, get_session, get_calendar_service
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")


@app.route("/")
def index():
    token = session.get("session_token")
    if token:
        user = get_session(token)
        if user:
            service = get_calendar_service(token)
            events = []
            if service:
                now = datetime.now(timezone.utc).isoformat()
                result = service.events().list(
                    calendarId="primary",
                    timeMin=now,
                    maxResults=20,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                events = result.get("items", [])
            return render_template("home.html", email=user["email"], events=events)
    return render_template("login.html")


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
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow HTTP for local dev
    app.run(debug=True, port=8080)
