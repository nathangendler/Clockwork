import { useState, useEffect } from "react";
import Header from "./components/Header";
import Tabs from "./components/Tabs";
import CalendarTab from "./components/CalendarTab";
import InviteTab from "./components/InviteTab";
import "./App.css";

function App() {
  const [email, setEmail] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("calendar");

  // --- Load token and email from chrome storage on mount ---
  useEffect(() => {
    chrome.storage.local.get(["token", "email"], ({ token, email }) => {
      if (email) setEmail(email);
      if (token) setToken(token);
      setLoading(false);
    });
  }, []);

  // --- Google Login ---
  function handleGoogleLogin() {
    const clientId =
      "674866953178-lst3r3er2pvjji1o8rji9loepe2qb8rp.apps.googleusercontent.com";
    const redirectUrl = `https://${chrome.runtime.id}.chromiumapp.org/`;
    const scopes = [
      "https://www.googleapis.com/auth/calendar.readonly",
      "https://www.googleapis.com/auth/calendar.events",
      "https://www.googleapis.com/auth/directory.readonly",
      "openid",
      "https://www.googleapis.com/auth/userinfo.email",
    ].join("%20");
    const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?client_id=${clientId}&redirect_uri=${redirectUrl}&response_type=code&scope=${scopes}&access_type=offline&prompt=consent`;

    chrome.identity.launchWebAuthFlow(
      { url: authUrl, interactive: true },
      (responseUrl) => {
        if (chrome.runtime.lastError) {
          console.error("Auth Error:", chrome.runtime.lastError);
          return;
        }

        const url = new URL(responseUrl);
        const code = url.searchParams.get("code");
        if (!code) {
          console.error("No code returned from Google");
          return;
        }

        // Exchange code for token
        fetch("http://localhost:8080/auth/token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, redirectUri: redirectUrl }),
        })
          .then((res) => res.json())
          .then((data) => {
            chrome.storage.local.set(
              { token: data.token, email: data.email },
              () => {
                setToken(data.token);
                setEmail(data.email);
                window.location.reload();
              },
            );
          })
          .catch(console.error);
      },
    );
  }

  // --- Logout ---
  function handleLogout() {
    chrome.storage.local.remove(["token", "email"], () => {
      setToken(null);
      setEmail(null);
    });
  }

  if (loading) return null;

  if (!email || !token) {
    return (
      <div className="login-container">
        <div className="login-card">
          <h1>Clockwork</h1>
          <p className="login-desc">Sign in to manage your calendar</p>

          <button className="btn-google" onClick={handleGoogleLogin}>
            Sign in with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <Header email={email} onLogout={handleLogout} />
      <Tabs activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="content">
        {activeTab === "calendar" ? (
          <CalendarTab token={token} />
        ) : (
          <InviteTab token={token} />
        )}
      </div>
    </div>
  );
}

export default App;
