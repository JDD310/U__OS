import { createContext, useContext, useReducer } from 'react';

const AppContext = createContext(null);

const MAX_LIVE_EVENTS = 200;

const initialState = {
  conflicts: [],
  selectedConflictId: null,
  events: [],
  liveEvents: [],
  sources: [],
  highlightedEventId: null,
  selectedMessage: null,
  wsConnected: false,
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_CONFLICTS':
      return { ...state, conflicts: action.payload };

    case 'SELECT_CONFLICT':
      return {
        ...state,
        selectedConflictId: action.payload,
        events: [],
        liveEvents: [],
        highlightedEventId: null,
        selectedMessage: null,
      };

    case 'SET_EVENTS':
      return { ...state, events: action.payload };

    case 'PUSH_LIVE_EVENT':
      return {
        ...state,
        liveEvents: [action.payload, ...state.liveEvents].slice(0, MAX_LIVE_EVENTS),
      };

    case 'SET_SOURCES':
      return { ...state, sources: action.payload };

    case 'HIGHLIGHT_EVENT':
      return {
        ...state,
        highlightedEventId:
          state.highlightedEventId === action.payload ? null : action.payload,
        selectedMessage: null,
      };

    case 'SET_MESSAGE_DETAIL':
      return { ...state, selectedMessage: action.payload };

    case 'CLEAR_HIGHLIGHT':
      return { ...state, highlightedEventId: null, selectedMessage: null };

    case 'SET_WS_STATUS':
      return { ...state, wsConnected: action.payload };

    default:
      return state;
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
}
