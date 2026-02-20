import { useEffect, useRef } from 'react';
import { LiveSocket } from '../api/websocket';
import { useAppContext } from '../context/AppContext';

export function useLiveFeed() {
  const { state, dispatch } = useAppContext();
  const socketRef = useRef(null);

  useEffect(() => {
    const socket = new LiveSocket(
      (event) => dispatch({ type: 'PUSH_LIVE_EVENT', payload: event }),
      (connected) => dispatch({ type: 'SET_WS_STATUS', payload: connected }),
    );
    socket.connect();
    socketRef.current = socket;
    return () => socket.disconnect();
  }, [dispatch]);

  const selectedConflict = state.conflicts.find(
    (c) => c.id === state.selectedConflictId,
  );

  useEffect(() => {
    if (socketRef.current && selectedConflict) {
      socketRef.current.subscribe([selectedConflict.short_code]);
    }
  }, [selectedConflict?.short_code]);
}
