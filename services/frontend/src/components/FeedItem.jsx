import { forwardRef, useState } from 'react';
import { useAppContext } from '../context/AppContext';
import { getEventColor, EVENT_TYPE_COLORS } from '../utils/colors';
import { formatTimestamp } from '../utils/time';
import { hasValidCoordinates } from '../utils/geo';
import { classifyMessage } from '../api/client';

const EVENT_TYPES = Object.keys(EVENT_TYPE_COLORS);

const FeedItem = forwardRef(function FeedItem({ event, isLive, isUnclassified, onClassified }, ref) {
  const { state, dispatch } = useAppContext();
  const [expanded, setExpanded] = useState(false);
  const [classifyConflict, setClassifyConflict] = useState('');
  const [classifyType, setClassifyType] = useState('statement');
  const [classifying, setClassifying] = useState(false);

  const eventId = event.id ?? event.event_id;
  const isHighlighted = state.highlightedEventId === eventId;
  const hasCoords = hasValidCoordinates(event);
  const eventType = event.event_type || 'unknown';
  const text = event.text ?? '';
  const location = event.location_name ?? event.location ?? '';
  const source = event.source_display_name || event.source_identifier || '';
  const platform = event.source_platform || event.platform || '';

  const handleClick = () => {
    setExpanded((prev) => !prev);
    if (!isUnclassified) {
      dispatch({ type: 'HIGHLIGHT_EVENT', payload: eventId });
    }
  };

  const handleClassify = async (e) => {
    e.stopPropagation();
    if (!classifyConflict || classifying) return;
    setClassifying(true);
    try {
      await classifyMessage(event.id, parseInt(classifyConflict), classifyType);
      onClassified?.(event.id);
    } catch (err) {
      console.error('Classification failed:', err);
    } finally {
      setClassifying(false);
    }
  };

  return (
    <div
      ref={ref}
      className={`feed-item ${isHighlighted ? 'highlighted' : ''} ${isLive ? 'live' : ''} ${expanded ? 'expanded' : ''}`}
      onClick={handleClick}
    >
      <div className="feed-item-row">
        <span className="feed-time">{formatTimestamp(event.timestamp)}</span>
        {platform && <span className="feed-platform-badge">{platform === 'telegram' ? 'TG' : 'X'}</span>}
        {source && <span className="feed-source">{source}</span>}
        {!isUnclassified && (
          <span
            className="feed-type-badge"
            style={{ background: getEventColor(eventType) }}
          >
            {eventType.replace('_', ' ')}
          </span>
        )}
        <span className="feed-text">{text.slice(0, 120)}{text.length > 120 ? '...' : ''}</span>
        {location && <span className="feed-location">{location}</span>}
        {!isUnclassified && !hasCoords && <span className="feed-no-loc" title="No coordinates">--</span>}
      </div>

      {expanded && (
        <div className="feed-expanded" onClick={(e) => e.stopPropagation()}>
          <div className="feed-full-text">{text || '(no text)'}</div>
          {location && <div className="feed-expanded-location">{location}</div>}

          {isUnclassified && (
            <div className="feed-classify-form">
              <select
                value={classifyConflict}
                onChange={(e) => setClassifyConflict(e.target.value)}
              >
                <option value="">Select conflict...</option>
                {state.conflicts.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <select
                value={classifyType}
                onChange={(e) => setClassifyType(e.target.value)}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>{t.replace('_', ' ')}</option>
                ))}
              </select>
              <button
                className="classify-btn"
                onClick={handleClassify}
                disabled={!classifyConflict || classifying}
              >
                {classifying ? '...' : 'Classify'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default FeedItem;
