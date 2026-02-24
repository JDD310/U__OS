import { useRef, useEffect, useMemo, useCallback, createRef, useState } from 'react';
import { useAppContext } from '../context/AppContext';
import { fetchUnclassifiedMessages } from '../api/client';
import FeedItem from './FeedItem';

export default function LiveFeed() {
  const { state } = useAppContext();
  const containerRef = useRef(null);
  const itemRefs = useRef({});
  const [tab, setTab] = useState('events');
  const [unclassified, setUnclassified] = useState([]);
  const [unclassifiedTotal, setUnclassifiedTotal] = useState(0);

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

  useEffect(() => {
    if (tab !== 'unclassified') return;
    fetchUnclassifiedMessages({ limit: 100 })
      .then((data) => {
        setUnclassified(data.messages);
        setUnclassifiedTotal(data.total);
      })
      .catch((err) => console.error('Failed to fetch unclassified:', err));
  }, [tab]);

  const handleClassified = (messageId) => {
    setUnclassified((prev) => prev.filter((m) => m.id !== messageId));
    setUnclassifiedTotal((prev) => prev - 1);
  };

  return (
    <div className="live-feed">
      <div className="feed-header">
        <button
          className={`feed-tab ${tab === 'events' ? 'active' : ''}`}
          onClick={() => setTab('events')}
        >
          EVENTS
        </button>
        <button
          className={`feed-tab ${tab === 'unclassified' ? 'active' : ''}`}
          onClick={() => setTab('unclassified')}
        >
          UNCLASSIFIED
          {unclassifiedTotal > 0 && <span className="feed-tab-count">{unclassifiedTotal}</span>}
        </button>
        {tab === 'events' && state.wsConnected && <span className="feed-pulse" />}
        <span className="feed-count">
          {tab === 'events' ? `${allEvents.length} events` : `${unclassified.length} messages`}
        </span>
      </div>
      <div className="feed-list" ref={containerRef}>
        {tab === 'events' && (
          <>
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
          </>
        )}
        {tab === 'unclassified' && (
          <>
            {unclassified.map((msg) => (
              <FeedItem
                key={msg.id}
                event={msg}
                isUnclassified
                onClassified={handleClassified}
              />
            ))}
            {unclassified.length === 0 && (
              <div className="feed-empty">No unclassified messages</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
