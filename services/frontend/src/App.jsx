import './App.css';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import MapView from './components/MapView';
import LiveFeed from './components/LiveFeed';
import { useConflicts } from './hooks/useConflicts';
import { useEvents } from './hooks/useEvents';
import { useLiveFeed } from './hooks/useLiveFeed';

export default function App() {
  useConflicts();
  useEvents();
  useLiveFeed();

  return (
    <div className="app">
      <Header />
      <div className="app-body">
        <Sidebar />
        <main className="main-panel">
          <MapView />
          <LiveFeed />
        </main>
      </div>
    </div>
  );
}
