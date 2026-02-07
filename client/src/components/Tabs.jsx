export default function Tabs({ activeTab, onTabChange }) {
  return (
    <div className="tabs">
      <button
        className={`tab ${activeTab === 'calendar' ? 'active' : ''}`}
        onClick={() => onTabChange('calendar')}
      >
        Calendar
      </button>
      <button
        className={`tab ${activeTab === 'invite' ? 'active' : ''}`}
        onClick={() => onTabChange('invite')}
      >
        Invite
      </button>
    </div>
  );
}
