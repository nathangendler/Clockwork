import { useState } from 'react';

export default function AIScheduleBar() {
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState(null); // null | 'loading' | 'success' | 'error'
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    if (!prompt.trim() || status === 'loading') return;

    setStatus('loading');
    setResult(null);
    setErrorMsg('');

    fetch('/api/events/ai-create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ prompt: prompt.trim() }),
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error || data.message || 'Failed to schedule');
        }
        return data;
      })
      .then(data => {
        setStatus('success');
        setResult(data);
        setPrompt('');
      })
      .catch(err => {
        setStatus('error');
        setErrorMsg(err.message);
      });
  }

  function formatMeetingTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  return (
    <div className="ai-schedule-bar">
      <div className="ai-schedule-header">
        <span className="ai-schedule-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2a4 4 0 0 1 4 4c0 1.5-.8 2.8-2 3.4V11h3a3 3 0 0 1 3 3v1" />
            <path d="M8 9.4A4 4 0 1 1 12 6" />
            <path d="M12 11v4" />
            <circle cx="12" cy="18" r="2" />
          </svg>
        </span>
        <span className="ai-schedule-label">Schedule with AI</span>
      </div>

      <form onSubmit={handleSubmit} className="ai-schedule-form">
        <input
          type="text"
          className="ai-schedule-input"
          placeholder='Try "lunch with John Smith" or "quick sync with Alice tomorrow"'
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          disabled={status === 'loading'}
        />
        <button
          type="submit"
          className="ai-schedule-submit"
          disabled={!prompt.trim() || status === 'loading'}
        >
          {status === 'loading' ? (
            <span className="ai-schedule-spinner" />
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 2L11 13" />
              <path d="M22 2L15 22L11 13L2 9L22 2Z" />
            </svg>
          )}
        </button>
      </form>

      {status === 'loading' && (
        <div className="ai-schedule-status ai-schedule-loading">
          Scheduling with AI...
        </div>
      )}

      {status === 'success' && result && (
        <div className="ai-schedule-status ai-schedule-success">
          <strong>{result.confirmed_meeting?.title}</strong> scheduled for{' '}
          {formatMeetingTime(result.confirmed_meeting?.start_time)}
          {result.resolved_contacts && (
            <div className="ai-schedule-contacts">
              {result.resolved_contacts.map((c, i) => (
                <span key={i} className="ai-schedule-contact-chip">{c}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {status === 'error' && (
        <div className="ai-schedule-status ai-schedule-error">
          {errorMsg}
        </div>
      )}
    </div>
  );
}
