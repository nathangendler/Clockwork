import { useState, useEffect, useRef } from 'react';

export default function NotificationDropdown() {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);

  // Fetch unread count on mount and periodically
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000); // Poll every 30 seconds
    return () => clearInterval(interval);
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function fetchUnreadCount() {
    fetch('/api/notifications/unread-count', { credentials: 'include' })
      .then(res => res.json())
      .then(data => setUnreadCount(data.count || 0))
      .catch(() => {});
  }

  function fetchNotifications() {
    setLoading(true);
    fetch('/api/notifications', { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        setNotifications(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }

  function handleToggle() {
    if (!isOpen) {
      fetchNotifications();
    }
    setIsOpen(!isOpen);
  }

  function handleRespond(notificationId, response) {
    fetch(`/api/notifications/${notificationId}/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ response }),
    })
      .then(res => res.json())
      .then(() => {
        fetchNotifications();
        fetchUnreadCount();
      })
      .catch(() => {});
  }

  function formatTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
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
    <div className="notification-container" ref={dropdownRef}>
      {/* Bell Icon */}
      <button className="notification-bell" onClick={handleToggle}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span className="notification-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <div className="notification-dropdown">
          <div className="notification-header">
            <h3>Notifications</h3>
          </div>

          <div className="notification-list">
            {loading ? (
              <div className="notification-empty">Loading...</div>
            ) : notifications.length === 0 ? (
              <div className="notification-empty">No notifications yet</div>
            ) : (
              notifications.map(notification => (
                <div
                  key={notification.id}
                  className={`notification-item ${!notification.is_read ? 'unread' : ''} ${notification.response ? 'responded' : ''}`}
                >
                  {/* LinkedIn-style avatar */}
                  <div className="notification-avatar">
                    {notification.meeting?.organizer_name?.[0]?.toUpperCase() || '?'}
                  </div>

                  <div className="notification-content">
                    <div className="notification-text">
                      <span className="notification-sender">
                        {notification.meeting?.organizer_name || notification.meeting?.organizer_email}
                      </span>
                      {' invited you to a meeting'}
                    </div>

                    <div className="notification-meeting-title">
                      {notification.meeting?.title}
                    </div>

                    <div className="notification-meeting-time">
                      {formatMeetingTime(notification.meeting?.start_time)}
                      {notification.meeting?.location && (
                        <span> · {notification.meeting.location}</span>
                      )}
                    </div>

                    <div className="notification-time">
                      {formatTime(notification.created_at)}
                    </div>

                    {/* Accept/Decline buttons - LinkedIn style */}
                    {!notification.response ? (
                      <div className="notification-actions">
                        <button
                          className="notification-btn notification-btn-ignore"
                          onClick={() => handleRespond(notification.id, 'declined')}
                        >
                          Decline
                        </button>
                        <button
                          className="notification-btn notification-btn-accept"
                          onClick={() => handleRespond(notification.id, 'accepted')}
                        >
                          Accept
                        </button>
                      </div>
                    ) : (
                      <div className="notification-response-status">
                        {notification.response === 'accepted' ? (
                          <span className="response-accepted">Accepted</span>
                        ) : (
                          <span className="response-declined">Declined</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Unread indicator dot */}
                  {!notification.is_read && <div className="notification-unread-dot" />}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
