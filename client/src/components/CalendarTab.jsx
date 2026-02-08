import { useState, useEffect } from "react";
import InviteTab from "./InviteTab";

export default function CalendarTab({ onInviteClick, activeTab }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scheduleQuery, setScheduleQuery] = useState("");
  const [scheduleMode, setScheduleMode] = useState(null);
  const [aiStatus, setAiStatus] = useState(null); // null | 'loading' | 'success' | 'error'
  const [aiResult, setAiResult] = useState(null);
  const [aiError, setAiError] = useState("");

  function fetchEvents() {
    fetch("/api/events", { credentials: "include" })
      .then((res) => res.json())
      .then((data) => {
        setEvents(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, 10000);
    return () => clearInterval(interval);
  }, []);

  const TZ = "America/New_York";

  function toEST(isoString) {
    if (!isoString) return { date: "", time: "" };
    const d = new Date(isoString);
    const date = d.toLocaleDateString("en-CA", { timeZone: TZ });
    const time = d.toLocaleTimeString("en-US", {
      timeZone: TZ,
      hour: "numeric",
      minute: "2-digit",
    });
    return { date, time };
  }

  function handleAiSchedule() {
    if (!scheduleQuery.trim() || aiStatus === 'loading') return;
    setAiStatus('loading');
    setAiResult(null);
    setAiError('');

    fetch('/api/events/ai-create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ prompt: scheduleQuery.trim() }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || data.message || 'Failed to schedule');
        return data;
      })
      .then((data) => {
        setAiStatus('success');
        setAiResult(data);
        setScheduleQuery('');
        fetchEvents();
      })
      .catch((err) => {
        setAiStatus('error');
        setAiError(err.message);
      });
  }

  function formatAiTime(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', {
      timeZone: TZ,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  function handleDelete(eventId) {
    fetch(`/api/events/${eventId}`, {
      method: "DELETE",
      credentials: "include",
    })
      .then((res) => {
        if (res.ok) {
          setEvents((prev) => prev.filter((e) => e.id !== eventId));
        }
      })
      .catch(() => {});
  }

  let currentDate = "";

  return (
    <div className="calendar-tab">
      {activeTab === "calendar" && (
        <section className="calendar-hero">
          <h2 className="calendar-hero-title">
            Streamline your scheduling with Clockwork
          </h2>
          <p className="calendar-hero-subtitle">
            Easily find the best meeting times for your team.
          </p>
          {activeTab === "calendar" && (
            <div className="calendar-hero-actions">
              <button
                type="button"
                className={
                  scheduleMode === "manual" ? "btn-primary" : "btn-secondary"
                }
                onClick={() =>
                  setScheduleMode(scheduleMode === "manual" ? null : "manual")
                }
              >
                <span className="btn-primary-icon"></span>
                Schedule Manually
              </button>

              <button
                type="button"
                className={
                  scheduleMode === "ai" ? "btn-primary" : "btn-secondary"
                }
                onClick={() =>
                  setScheduleMode(scheduleMode === "ai" ? null : "ai")
                }
              >
                <span className="btn-primary-icon"></span>
                Schedule with AI
              </button>
            </div>
          )}
          {scheduleMode === "manual" && <InviteTab></InviteTab>}
          {scheduleMode === "ai" && (
            <div>
              <div className="scheduling-input-wrap">
                <input
                  type="text"
                  className="scheduling-input"
                  placeholder='Try "lunch with John Smith" or "quick sync with Alice tomorrow"'
                  value={scheduleQuery}
                  onChange={(e) => setScheduleQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAiSchedule()}
                  disabled={aiStatus === 'loading'}
                  aria-label="What would you like to schedule?"
                />
                <button
                  type="button"
                  className="scheduling-submit"
                  onClick={handleAiSchedule}
                  disabled={!scheduleQuery.trim() || aiStatus === 'loading'}
                  aria-label="Submit"
                >
                  {aiStatus === 'loading' ? (
                    <span className="ai-spinner" />
                  ) : (
                    <span aria-hidden>→</span>
                  )}
                </button>
              </div>

              {aiStatus === 'loading' && (
                <div className="ai-status ai-status-loading">
                  Scheduling with AI...
                </div>
              )}

              {aiStatus === 'success' && aiResult && (
                <div className="ai-status ai-status-success">
                  <strong>{aiResult.confirmed_meeting?.title}</strong> scheduled for{' '}
                  {formatAiTime(aiResult.confirmed_meeting?.start_time)}
                </div>
              )}

              {aiStatus === 'error' && (
                <div className="ai-status ai-status-error">
                  {aiError}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {activeTab === "settings" && (
        <>
          {loading ? (
            <div className="no-events">Loading events...</div>
          ) : events.length > 0 ? (
            <section className="calendar-events">
              {events.map((event) => {
                const start = toEST(event.start_time);
                const end = toEST(event.end_time);
                const datePart = start.date;
                const showDateHeader = datePart !== currentDate;
                if (showDateHeader) currentDate = datePart;
                const startTime = start.time;
                const endTime = end.time;

                return (
                  <div key={event.id}>
                    {showDateHeader && (
                      <div className="date-header">{datePart}</div>
                    )}

                    <div className="event-card">
                      <div className="event-card-header">
                        <div className="event-time">
                          {startTime} – {endTime}
                        </div>
                        <button
                          className="btn-delete"
                          onClick={() => handleDelete(event.id)}
                          title="Delete meeting"
                        >
                          ×
                        </button>
                      </div>
                      <div className="event-details">
                        <div className="event-title">
                          {event.title || "(No title)"}
                        </div>
                        <div className="event-meta">
                          <span>{event.duration_minutes} min</span>
                          <span
                            className={`urgency-badge urgency-${event.urgency.toLowerCase()}`}
                          >
                            {event.urgency}
                          </span>
                        </div>
                        {event.description && (
                          <div className="event-description">
                            {event.description}
                          </div>
                        )}
                        {event.location && (
                          <div className="event-location">
                            <span className="location-icon">📍</span>
                            {event.location}
                          </div>
                        )}
                        {event.invites && event.invites.length > 0 && (
                          <div className="event-attendees">
                            {event.invites.map((inv) => (
                              <span
                                key={inv.id}
                                className={`attendee-chip status-${inv.status}`}
                              >
                                {inv.name || inv.email}
                                <span className="attendee-status">
                                  {inv.status === "accepted"
                                    ? "✓"
                                    : inv.status === "declined"
                                      ? "✗"
                                      : "…"}
                                </span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </section>
          ) : (
            <div className="no-events">No meetings pending acceptance.</div>
          )}
        </>
      )}
    </div>
  );
}
