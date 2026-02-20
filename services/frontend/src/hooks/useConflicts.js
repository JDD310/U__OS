import { useEffect } from 'react';
import { fetchConflicts, fetchSources } from '../api/client';
import { useAppContext } from '../context/AppContext';

export function useConflicts() {
  const { state, dispatch } = useAppContext();

  useEffect(() => {
    fetchConflicts()
      .then((data) => {
        dispatch({ type: 'SET_CONFLICTS', payload: data });
        if (data.length > 0 && !state.selectedConflictId) {
          dispatch({ type: 'SELECT_CONFLICT', payload: data[0].id });
        }
      })
      .catch((err) => console.error('Failed to fetch conflicts:', err));

    fetchSources()
      .then((data) => dispatch({ type: 'SET_SOURCES', payload: data }))
      .catch((err) => console.error('Failed to fetch sources:', err));
  }, []);
}
