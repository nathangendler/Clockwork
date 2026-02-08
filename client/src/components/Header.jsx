import NotificationDropdown from "./NotificationDropdown";

function LogoIcon() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M12 15.5A3.5 3.5 0 0 1 8.5 12 3.5 3.5 0 0 1 12 8.5a3.5 3.5 0 0 1 3.5 3.5 3.5 3.5 0 0 1-3.5 3.5m7.43-2.53c.04-.32.07-.65.07-.97 0-.32-.03-.66-.07-1l2.11-1.63c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.31-.61-.22l-2.49 1c-.52-.39-1.06-.73-1.69-.98l-.37-2.65A.506.506 0 0 0 14 2h-4c-.25 0-.46.18-.5.42l-.37 2.65c-.63.25-1.17.59-1.69.98l-2.49-1c-.22-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64L4.57 11c-.04.34-.07.68-.07 1 0 .32.03.65.07.97l-2.11 1.66c-.19.15-.25.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1.01c.52.4 1.06.74 1.69.99l.37 2.65c.04.24.25.42.5.42h4c.25 0 .46-.18.5-.42l.37-2.65c.63-.26 1.17-.59 1.69-.99l2.49 1.01c.22.08.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.66z"
        fill="#1a73e8"
      />
    </svg>
  );
}

export default function Header({ email, onLogout }) {
  return (
    <header className="header">
      <div className="header-left">
        <div className="header-logo">
          <LogoIcon />
          <h1>Clockwork</h1>
        </div>
        <div className="header-workspace">
          <span className="workspace-label">Workspace:</span>
          <button type="button" className="workspace-dropdown" aria-haspopup="listbox">
            Lion Dine
            <span className="workspace-chevron" aria-hidden>▼</span>
          </button>
        </div>
      </div>
      <div className="header-right">
        <span className="header-email">{email}</span>
        <span className="header-role">Admin</span>
        <button type="button" className="btn-signout" onClick={onLogout}>
          Sign out
        </button>
        <NotificationDropdown />
        <button type="button" className="header-more" aria-label="More options">
          <span aria-hidden>⋯</span>
        </button>
      </div>
    </header>
  );
}
