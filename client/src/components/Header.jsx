import NotificationDropdown from "./NotificationDropdown";
import Logo from "../assets/Logo.png";

function LogoIcon() {
  return (
    <img
      src={Logo}
      alt="Logo"
      width={28}
      height={28}
      style={{ display: "block" }}
    />
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
        <div className="header-workspace"></div>
      </div>
      <div className="header-right">
        <span className="header-email">{email}</span>

        <button type="button" className="btn-signout" onClick={onLogout}>
          Sign out
        </button>
        <NotificationDropdown />
      </div>
    </header>
  );
}
