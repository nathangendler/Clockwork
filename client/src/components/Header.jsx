
import NotificationDropdown from './NotificationDropdown';

export default function Header({ email, onLogout }) {
  return (
    <div className="header">
      <h1>Clockwork</h1>
      <div className="header-right">
        <NotificationDropdown />
        <span className="email">{email}</span>
        <button className="btn-logout" onClick={onLogout}>
          Sign Out
        </button>
      </div>
    </div>
  );
}
