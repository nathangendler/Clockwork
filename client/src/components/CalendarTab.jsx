import { useState, useEffect } from 'react';

export default function CalendarTab() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/events', { credentials: 'include' })
      .then(res => res.json())
      .then(data => { setEvents(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="no-events">Loading events...</div>;
  if (events.length === 0) return <div className="no-events">No upcoming events on your calendar.</div>;

  let currentDate = '';

  return (
    <div>
      {events.map((event) => {
        const start = event.start || {};
        const startDt = start.dateTime || start.date || '';
        const datePart = startDt.slice(0, 10);
        const showDateHeader = datePart !== currentDate;
        if (showDateHeader) currentDate = datePart;

        return (
          <div key={event.id}>
            {showDateHeader && <div className="date-header">{datePart}</div>}
            <div className="event-card">
              <div className="event-time">
                {start.dateTime ? startDt.slice(11, 16) : 'All day'}
              </div>
              <div className="event-details">
                <div className="event-title">{event.summary || '(No title)'}</div>
                {event.location && <div className="event-location">{event.location}</div>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
