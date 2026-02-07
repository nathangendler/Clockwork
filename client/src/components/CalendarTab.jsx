import { useState, useEffect } from 'react';

export default function CalendarTab() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  function loadEvents() {
    fetch('/api/events', { credentials: 'include' })
      .then(res => res.json())
      .then(data => { setEvents(data); setLoading(false); })
      .catch(() => setLoading(false));
  }

  useEffect(() => { loadEvents(); }, []);

  function handleDelete(id) {
    fetch(`/api/events/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
      .then(res => {
        if (res.ok) {
          setEvents(prev => prev.filter(e => e.id !== id));
        }
      });
  }

  if (loading) return <div className="no-events">Loading events...</div>;
  if (events.length === 0) return <div className="no-events">No meetings scheduled.</div>;

  let currentDate = '';

  return (
    <div>
      {events.map((event) => {
        const startDt = event.start_time || '';
        const endDt = event.end_time || '';
        const datePart = startDt.slice(0, 10);
        const showDateHeader = datePart !== currentDate;
        if (showDateHeader) currentDate = datePart;

        const startTime = startDt.slice(11, 16);
        const endTime = endDt.slice(11, 16);

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
                      <span key={inv.id} className="attendee-chip">{inv.name || inv.email}</span>
                    ))}
                  </div>
                )}
              </div>
              <button
                className="btn-delete"
                onClick={() => handleDelete(event.id)}
                title="Delete meeting"
              >
                X
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
