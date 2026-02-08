import { useState, useEffect } from 'react';
import Header from './components/Header';
import Tabs from './components/Tabs';
import CalendarTab from './components/CalendarTab';
import InviteTab from './components/InviteTab';
import './App.css';

// Detect if running as Chrome extension
const isExtension = typeof chrome !== 'undefined' && chrome.storage && chrome.identity;
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8080";

function App() {
  const [email, setEmail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('calendar');

  useEffect(() => {
    if (isExtension) {
      // Chrome extension mode - check stored session
      chrome.storage.local.get(['sessionToken', 'email'], (result) => {
        if (result.sessionToken && result.email) {
          setEmail(result.email);
        }
        setLoading(false);
      });
    } else {
      // Browser dev mode - use Flask session cookies
      fetch(`${API_BASE}/api/me`, { credentials: 'include' })
        .then(res => {
          if (!res.ok) throw new Error('not authed');
          return res.json();
        })
        .then(data => { setEmail(data.email); setLoading(false); })
        .catch(() => setLoading(false));
    }
  }, []);

  function handleGoogleLogin() {
    if (isExtension) {
      // Chrome extension OAuth flow using launchWebAuthFlow
      const clientId = "674866953178-lst3r3er2pvjji1o8rji9loepe2qb8rp.apps.googleusercontent.com";
      const redirectUrl = chrome.identity.getRedirectURL();
      const scopes = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/directory.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
      ].join(" ");

      const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
        `client_id=${clientId}` +
        `&redirect_uri=${encodeURIComponent(redirectUrl)}` +
        `&response_type=code` +
        `&scope=${encodeURIComponent(scopes)}` +
        `&access_type=offline` +
        `&prompt=consent`;

      chrome.identity.launchWebAuthFlow(
        { url: authUrl, interactive: true },
        (responseUrl) => {
          if (chrome.runtime.lastError) {
            console.error("Auth Error:", chrome.runtime.lastError);
            return;
          }
          if (!responseUrl) {
            console.error("No response URL");
            return;
          }

          const url = new URL(responseUrl);
          const code = url.searchParams.get("code");
          if (!code) {
            console.error("No code in response");
            return;
          }

          // Exchange code for session token via backend
          fetch(`${API_BASE}/auth/extension/token`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code, redirectUri: redirectUrl }),
          })
            .then(res => res.json())
            .then(data => {
              if (data.session_token && data.email) {
                chrome.storage.local.set({
                  sessionToken: data.session_token,
                  email: data.email,
                }, () => {
                  setEmail(data.email);
                });
              } else {
                console.error("Token exchange failed:", data);
              }
            })
            .catch(err => console.error("Token exchange error:", err));
        }
      );
    } else {
      // Browser dev mode - redirect to Flask OAuth
      window.location.href = `${API_BASE}/auth/login`;
    }
  }

  function handleLogout() {
    if (isExtension) {
      chrome.storage.local.remove(['sessionToken', 'email'], () => {
        setEmail(null);
      });
    } else {
      window.location.href = `${API_BASE}/logout`;
    }
  }

  if (loading) return null;

  if (!email) {
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
        {activeTab === 'calendar' ? <CalendarTab /> : <InviteTab />}
      </div>
    </div>
  );
}

export default App;
