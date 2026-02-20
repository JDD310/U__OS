import { forwardRef } from 'react';
import { useAppContext } from '../context/AppContext';
import { getEventColor } from '../utils/colors';
import { formatTimestamp } from '../utils/time';
import { hasValidCoordinates } from '../utils/geo';

const FeedItem = forwardRef(function FeedItem({ event, isLive }, ref) {
  const { state, dispatch } = useAppContext();
  const eventId = event.id ?? event.event_id;
  const isHighlighted = state.highlightedEventId === eventId;
  const hasCoords = hasValidCoordinates(event);
  const eventType = event.event_type || 'unknown';
  const text = event.text ?? '';
  const location = event.location_name ?? event.location ?? '';

  return (
    <div
      ref={ref}
      className={`feed-item ${isHighlighted ? 'highlighted' : ''} ${isLive ? 'live' : ''}`}
      onClick={() => dispatch({ type: 'HIGHLIGHT_EVENT', payload: eventId })}
    >
      <span className="feed-time">{formatTimestamp(event.timestamp)}</span>
      <span
        className="feed-type-badge"
        style={{ background: getEventColor(eventType) }}
      >
        {eventType.replace('_', ' ')}
      </span>
      <span className="feed-text">{text.slice(0, 120)}{text.length > 120 ? '...' : ''}</span>
      {location && <span className="feed-location">{location}</span>}
      {!hasCoords && <span className="feed-no-loc" title="No coordinates">--</span>}
    </div>
  );
});

export default FeedItem;
