import { useEffect } from 'react';
import { fetchEvents } from '../api/client';
import { useAppContext } from '../context/AppContext';

export function useEvents() {
  const { state, dispatch } = useAppContext();

  useEffect(() => {
    if (!state.selectedConflictId) return;

    fetchEvents(state.selectedConflictId, { limit: 500 })
      .then((data) => dispatch({ type: 'SET_EVENTS', payload: data.events }))
      .catch((err) => console.error('Failed to fetch events:', err));
  }, [state.selectedConflictId]);
}
