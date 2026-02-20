import { useAppContext } from '../context/AppContext';
import ConflictCard from './ConflictCard';

export default function Sidebar() {
  const { state } = useAppContext();

  const telegramCount = state.sources.filter(
    (s) => s.platform === 'telegram',
  ).length;
  const xCount = state.sources.filter((s) => s.platform === 'x').length;

  return (
    <aside className="sidebar">
      <div className="sidebar-section">
        <div className="sidebar-label">CONFLICTS</div>
        <div className="conflict-list">
          {state.conflicts.map((c) => (
            <ConflictCard key={c.id} conflict={c} />
          ))}
          {state.conflicts.length === 0 && (
            <div className="sidebar-empty">No conflicts loaded</div>
          )}
        </div>
      </div>

      <div className="sidebar-section sidebar-sources">
        <div className="sidebar-label">SOURCES</div>
        <div className="source-counts">
          <span className="source-badge tg">TG: {telegramCount}</span>
          <span className="source-badge x">X: {xCount}</span>
        </div>
      </div>
    </aside>
  );
}
