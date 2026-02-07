import { useState } from "react";

export default function InviteTab({ token }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState([]);
  const [summary, setSummary] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [status, setStatus] = useState(null);
  const [searching, setSearching] = useState(false);

  function handleSearch(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);

    fetch(
      `http://localhost:8080/api/contacts/search?q=${encodeURIComponent(query)}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    )
      .then((res) => res.json())
      .then((data) => {
        setResults(data);
        setSearching(false);
      })
      .catch(() => setSearching(false));
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
    if (!start || !end || selected.length === 0) return;
    setStatus("creating");

    fetch("http://localhost:8080/api/events/create", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        summary: summary || "Meeting",
        start,
        end,
        attendees: selected.map((c) => c.email),
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.id) {
          setStatus("success");
          setSelected([]);
          setSummary("");
          setStart("");
          setEnd("");
          setResults([]);
          setQuery("");
        } else {
          setStatus("error");
        }
      })
      .catch(() => setStatus("error"));
  }

  return (
    <div>
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
          {searching ? "Searching..." : "Search"}
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
                {c.name || c.email} &times;
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
            <label className="form-label">Start</label>
            <input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="form-input"
              required
            />
            <label className="form-label">End</label>
            <input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="form-input"
              required
            />
            <button
              type="submit"
              className="btn-create"
              disabled={status === "creating"}
            >
              {status === "creating" ? "Creating..." : "Create Meeting"}
            </button>
          </form>

          {status === "success" && (
            <p className="success-msg">Meeting created and invites sent!</p>
          )}
          {status === "error" && (
            <p className="error-msg">Failed to create meeting. Try again.</p>
          )}
        </div>
      )}
    </div>
  );
}
