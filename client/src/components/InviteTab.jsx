import { useState } from "react";
import { api } from "../api";
import AIScheduleBar from "./AIScheduleBar";

export default function InviteTab() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState([]);
  const [summary, setSummary] = useState('');
  const [description, setDescription] = useState('');
  const [durationMinutes, setDurationMinutes] = useState('');
  const [locationType, setLocationType] = useState('online');
  const [onlinePlatform, setOnlinePlatform] = useState('');
  const [inPersonLocation, setInPersonLocation] = useState('');
  const [urgency, setUrgency] = useState('normal');
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');
  const [status, setStatus] = useState(null);
  const [searching, setSearching] = useState(false);

  function handleSearch(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);

    api(`/api/contacts/search?q=${encodeURIComponent(query)}`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setResults(data);
        } else {
          setResults([]);
        }
        setSearching(false);
      })
      .catch(() => {
        setResults([]);
        setSearching(false);
      });
  }

  function toggleSelect(contact) {
    setSelected((prev) => {
      const exists = prev.find((c) => c.email === contact.email);
      if (exists) return prev.filter((c) => c.email !== contact.email);
      return [...prev, contact];
    });
  }

  function handleCreate(e) {
    e.preventDefault();
    if (!windowStart || !windowEnd || selected.length === 0) return;
    setStatus('creating');

    const locationValue = locationType === 'in-person'
      ? (inPersonLocation || 'In person')
      : (onlinePlatform || 'Online');

    api('/api/events/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        summary: summary || 'Meeting',
        description,
        durationMinutes: parseInt(durationMinutes, 10) || 60,
        urgency,
        location: locationValue,
        start: windowStart,
        end: windowEnd,
        attendees: selected.map(c => c.email),
        locationType: locationType === 'in-person' ? 'in-person' : 'virtual',
      }),
    })
      .then(async res => ({ ok: res.ok, status: res.status, data: await res.json() }))
      .then(result => {
        if (result.ok) {
          setStatus('success');
          setSelected([]);
          setSummary('');
          setDescription('');
          setDurationMinutes('');
          setLocationType('online');
          setOnlinePlatform('');
          setInPersonLocation('');
          setUrgency('normal');
          setWindowStart('');
          setWindowEnd('');
          setResults([]);
          setQuery("");
        } else {
          if (result.status === 409 && result.data?.error === 'no_valid_slots') {
            alert('No available time slots were found for that window.');
          }
          setStatus('error');
        }
      })
      .catch(() => setStatus("error"));
  }

  return (
    <div>
      <AIScheduleBar />

      <div className="ai-schedule-divider">
        <span>or schedule manually</span>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="search-form">
        <input
          type="text"
          placeholder="Search contacts..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="search-input"
        />
        <button type="submit" className="btn-search" disabled={searching}>
          {searching ? "..." : "Search"}
        </button>
      </form>

      {/* Search results */}
      {results.length > 0 && (
        <div className="contact-results">
          {results.map((contact) => {
            const isSelected = selected.some((c) => c.email === contact.email);
            return (
              <div
                key={contact.email}
                className={`contact-card ${isSelected ? "selected" : ""}`}
                onClick={() => toggleSelect(contact)}
              >
                <div className="contact-name">
                  {contact.name || contact.email}
                </div>
                <div className="contact-email">{contact.email}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Selected contacts */}
      {selected.length > 0 && (
        <div className="selected-section">
          <h3>Inviting ({selected.length})</h3>
          <div className="selected-chips">
            {selected.map((c) => (
              <span
                key={c.email}
                className="chip"
                onClick={() => toggleSelect(c)}
              >
                {c.name || c.email} ×
              </span>
            ))}
          </div>

          {/* Meeting form */}
          <form onSubmit={handleCreate} className="meeting-form">
            <input
              type="text"
              placeholder="Meeting title"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              className="form-input"
            />
            <label className="form-label">Description</label>
            <textarea
              placeholder="Add details"
              value={description}
              onChange={e => setDescription(e.target.value)}
              className="form-textarea"
              rows={2}
            />
            <label className="form-label">Duration (min)</label>
            <input
              type="number"
              min="1"
              placeholder="30"
              value={durationMinutes}
              onChange={e => setDurationMinutes(e.target.value)}
              className="form-input"
            />
            <label className="form-label">Urgency</label>
            <div className="urgency-toggle">
              {['low', 'normal', 'high'].map(u => (
                <button
                  key={u}
                  type="button"
                  className={`urgency-button ${urgency === u ? 'active' : ''}`}
                  onClick={() => setUrgency(u)}
                >
                  {u.charAt(0).toUpperCase() + u.slice(1)}
                </button>
              ))}
            </div>
            <label className="form-label">Location</label>
            <div className="location-toggle">
              <label className="radio-pill">
                <input
                  type="radio"
                  name="locationType"
                  checked={locationType === 'online'}
                  onChange={() => setLocationType('online')}
                />
                <span>Online</span>
              </label>
              <label className="radio-pill">
                <input
                  type="radio"
                  name="locationType"
                  checked={locationType === 'in-person'}
                  onChange={() => setLocationType('in-person')}
                />
                <span>In person</span>
              </label>
            </div>
            {locationType === 'online' ? (
              <input
                type="text"
                placeholder="Platform (Zoom, Meet)"
                value={onlinePlatform}
                onChange={e => setOnlinePlatform(e.target.value)}
                className="form-input"
              />
            ) : (
              <input
                type="text"
                placeholder="Location"
                value={inPersonLocation}
                onChange={e => setInPersonLocation(e.target.value)}
                className="form-input"
              />
            )}
            <label className="form-label">Time Window</label>
            <div className="window-grid">
              <div>
                <label className="form-sub-label">Start</label>
                <input
                  type="datetime-local"
                  value={windowStart}
                  onChange={e => setWindowStart(e.target.value)}
                  className="form-input"
                  required
                />
              </div>
              <div>
                <label className="form-sub-label">End</label>
                <input
                  type="datetime-local"
                  value={windowEnd}
                  onChange={e => setWindowEnd(e.target.value)}
                  className="form-input"
                  required
                />
              </div>
            </div>
            <button type="submit" className="btn-create" disabled={status === 'creating'}>
              {status === 'creating' ? 'Creating...' : 'Create Meeting'}
            </button>
          </form>

          {status === "success" && (
            <p className="success-msg">Meeting created!</p>
          )}
          {status === "error" && (
            <p className="error-msg">Failed to create meeting.</p>
          )}
        </div>
      )}
    </div>
  );
}
