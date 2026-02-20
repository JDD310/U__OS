import { useRef, useEffect, useMemo, useCallback, createRef } from 'react';
import { useAppContext } from '../context/AppContext';
import FeedItem from './FeedItem';

export default function LiveFeed() {
  const { state } = useAppContext();
  const containerRef = useRef(null);
  const itemRefs = useRef({});

  const allEvents = useMemo(() => {
    const liveIds = new Set(state.liveEvents.map((e) => e.event_id));
    const historicalFiltered = state.events.filter((e) => !liveIds.has(e.id));
    return [
      ...state.liveEvents.map((e) => ({ ...e, _isLive: true })),
      ...historicalFiltered.map((e) => ({ ...e, _isLive: false })),
    ];
  }, [state.events, state.liveEvents]);

  const getRef = useCallback((eventId) => {
    if (!itemRefs.current[eventId]) {
      itemRefs.current[eventId] = createRef();
    }
    return itemRefs.current[eventId];
  }, []);

  useEffect(() => {
    const targetId = state.highlightedEventId;
    if (!targetId) return;
    const ref = itemRefs.current[targetId];
    if (ref?.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [state.highlightedEventId]);

  return (
    <div className="live-feed">
      <div className="feed-header">
        <span className="feed-title">LIVE FEED</span>
        {state.wsConnected && <span className="feed-pulse" />}
        <span className="feed-count">{allEvents.length} events</span>
      </div>
      <div className="feed-list" ref={containerRef}>
        {allEvents.map((event) => {
          const id = event.id ?? event.event_id;
          return (
            <FeedItem
              key={id}
              ref={getRef(id)}
              event={event}
              isLive={event._isLive}
            />
          );
        })}
        {allEvents.length === 0 && (
          <div className="feed-empty">No events for this conflict</div>
        )}
      </div>
    </div>
  );
}
