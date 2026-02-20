import { useAppContext } from '../context/AppContext';

export default function Header() {
  const { state } = useAppContext();

  return (
    <header className="header">
      <div className="header-title">OSINT SITUATION MONITOR</div>
      <div className="header-status">
        <span
          className={`status-dot ${state.wsConnected ? 'connected' : 'disconnected'}`}
        />
        <span className="status-text">
          {state.wsConnected ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>
    </header>
  );
}
