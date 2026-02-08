import { useState, useEffect } from "react";
import { api } from "../api";


export default function CalendarTab() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [userEmail, setUserEmail] = useState(null);

  function fetchEvents() {
    // Fetch current user and events in parallel
    Promise.all([
      api("/api/me").then((res) => res.json()),
      api("/api/events").then((res) => res.json()),
    ])
      .then(([userData, eventsData]) => {
        setUserEmail(userData.email);
        setEvents(eventsData);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="no-events">Loading events...</div>;
  if (events.length === 0)
    return (
      <div className="no-events">No pending events on your calendar.</div>
    );

  const TZ = "America/New_York";

  function toEST(isoString) {
    if (!isoString) return { date: "", time: "" };
    const d = new Date(isoString);
    const date = d.toLocaleDateString("en-CA", { timeZone: TZ }); // YYYY-MM-DD
    const time = d.toLocaleTimeString("en-US", {
      timeZone: TZ,
      hour: "numeric",
      minute: "2-digit",
    });
    return { date, time };
  }

  function handleDelete(eventId) {
    // Optimistic update - remove from UI immediately
    const previousEvents = events;
    setEvents(events.filter((e) => e.id !== eventId));

    api(`/api/events/${eventId}`, { method: 'DELETE' })
      .then((res) => {
        if (!res.ok) {
          // Revert on error
          setEvents(previousEvents);
        }
      })
      .catch(() => {
        // Revert on error
        setEvents(previousEvents);
      });
  }

  let currentDate = "";

  return (
    <div>
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
            {showDateHeader && <div className="date-header">{datePart}</div>}
            <div className="event-card">
              <div className="event-time">
                {startTime} – {endTime}
              </div>
              <div className="event-details">
                <div className="event-title">{event.title || '(No title)'}</div>
                <div className="event-meta">{event.duration_minutes} min · {event.urgency}</div>
                {event.description && <div className="event-description">{event.description}</div>}
                {event.location && <div className="event-location">{event.location}</div>}
                {event.invites && event.invites.length > 0 && (
                  <div className="event-attendees">
                    {event.invites.map(inv => (
                      <span key={inv.id} className={`attendee-chip status-${inv.status}`}>
                        {inv.name || inv.email}
                        <span className="attendee-status">
                          {inv.status === 'accepted' ? ' ✓' : inv.status === 'declined' ? ' ✗' : ' …'}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {event.organizer_email === userEmail && (
                <button
                  className="btn-delete"
                  onClick={() => handleDelete(event.id)}
                  title="Delete meeting"
                >
                  X
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
