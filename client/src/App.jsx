import { useState, useEffect } from "react";
import Header from "./components/Header";
import Tabs from "./components/Tabs";
import CalendarTab from "./components/CalendarTab";
import InviteTab from "./components/InviteTab";
import "./App.css";

function App() {
  const [email, setEmail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("calendar");

  // --- Load session on mount ---
  useEffect(() => {
    fetch("/api/me", { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("not authed");
        return res.json();
      })
      .then((data) => {
        setEmail(data.email);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function handleLogout() {
    window.location.href = "/logout";
  }

  if (loading) return null;

  if (!email) {
    return (
      <div className="login-container">
        <div className="login-card">
          <h1>Clockwork</h1>
          <p className="login-desc">Sign in to manage your calendar</p>

          <a href="/auth/login" className="btn-google">
            Sign in with Google
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <Header email={email} onLogout={handleLogout} />
      <div className="app-body">
        <Tabs activeTab={activeTab} onTabChange={setActiveTab} />
        <main className="content">
          {activeTab === "calendar" ? (
            <CalendarTab onInviteClick={() => setActiveTab("settings")} />
          ) : (
            <InviteTab />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
