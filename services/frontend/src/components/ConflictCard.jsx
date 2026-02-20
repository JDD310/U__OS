import { useAppContext } from '../context/AppContext';

export default function ConflictCard({ conflict }) {
  const { state, dispatch } = useAppContext();
  const isSelected = state.selectedConflictId === conflict.id;
  const scheme = conflict.color_scheme || {};

  return (
    <button
      className={`conflict-card ${isSelected ? 'selected' : ''}`}
      onClick={() => dispatch({ type: 'SELECT_CONFLICT', payload: conflict.id })}
    >
      <div className="conflict-name">{conflict.name}</div>
      <div className="conflict-colors">
        {scheme.allies && (
          <span
            className="color-swatch"
            style={{ background: scheme.allies.color }}
            title={`Allies: ${scheme.allies.countries.join(', ')}`}
          />
        )}
        {scheme.adversaries && (
          <span
            className="color-swatch"
            style={{ background: scheme.adversaries.color }}
            title={`Adversaries: ${scheme.adversaries.countries.join(', ')}`}
          />
        )}
        {scheme.involved && (
          <span
            className="color-swatch"
            style={{ background: scheme.involved.color }}
            title={`Involved: ${scheme.involved.countries.join(', ')}`}
          />
        )}
      </div>
    </button>
  );
}
