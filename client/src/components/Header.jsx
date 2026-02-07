export default function Header({ email }) {
  return (
    <div className="header">
      <h1>Clockwork</h1>
      <div className="header-right">
        <span className="email">{email}</span>
        <a href="/auth/login" className="btn-logout" onClick={(e) => {
          e.preventDefault();
          window.location.href = '/logout';
        }}>Sign Out</a>
      </div>
    </div>
  );
}
