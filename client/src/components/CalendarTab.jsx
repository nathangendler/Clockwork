import { useState, useEffect } from "react";

export default function CalendarTab({ onInviteClick }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scheduleQuery, setScheduleQuery] = useState("");

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
      <section className="calendar-hero">
        <h2 className="calendar-hero-title">
          Streamline your scheduling with Clockwork
        </h2>
        <p className="calendar-hero-subtitle">
          Easily find the best meeting times for your team.
        </p>
        <div className="calendar-hero-actions">
          <button type="button" className="btn-primary">
            <span className="btn-primary-icon">+</span>
            Create Meeting
          </button>
          <button type="button" className="btn-secondary">
            <span className="btn-secondary-icon" aria-hidden>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="24" height="24" rx="4" fill="#4285F4" />
                <path d="M6 8h12v2H6V8zm0 4h12v2H6v-2zm0 4h8v2H6v-2z" fill="white" />
              </svg>
            </span>
            Import Google Calendar
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={onInviteClick}
          >
            <span className="btn-secondary-icon" aria-hidden>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#5f6368" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </span>
            Invite Teammates
          </button>
        </div>
        <div className="scheduling-input-wrap">
          <input
            type="text"
            className="scheduling-input"
            placeholder="What would you like to schedule?"
            value={scheduleQuery}
            onChange={(e) => setScheduleQuery(e.target.value)}
            aria-label="What would you like to schedule?"
          />
          <button type="button" className="scheduling-submit" aria-label="Submit">
            <span aria-hidden>→</span>
          </button>
        </div>
        <div className="calendar-hero-secondary">
          <button type="button" className="btn-outline">Scheduling Tips</button>
          <button type="button" className="btn-outline">Analytics Overview</button>
          <button type="button" className="btn-outline">Manage Settings</button>
        </div>
      </section>

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
                  <div className="event-time">
                    {startTime} – {endTime}
                  </div>
                  <div className="event-details">
                    <div className="event-title">
                      {event.title || "(No title)"}
                    </div>
                    <div className="event-meta">
                      {event.duration_minutes} min · {event.urgency}
                    </div>
                    {event.description && (
                      <div className="event-description">{event.description}</div>
                    )}
                    {event.location && (
                      <div className="event-location">{event.location}</div>
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
                                ? " ✓"
                                : inv.status === "declined"
                                  ? " ✗"
                                  : " …"}
                            </span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn-delete"
                    onClick={() => handleDelete(event.id)}
                    title="Delete meeting"
                  >
                    ×
                  </button>
                </div>
              </div>
            );
          })}
        </section>
      ) : (
        <div className="no-events">No meetings pending acceptance.</div>
      )}
    </div>
  );
}
