import { WS_URL } from './client';

export class LiveSocket {
  constructor(onEvent, onStatusChange) {
    this.onEvent = onEvent;
    this.onStatusChange = onStatusChange;
    this.ws = null;
    this.subscriptions = [];
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.closed = false;
  }

  connect() {
    if (this.closed) return;

    try {
      this.ws = new WebSocket(WS_URL);
    } catch {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.onStatusChange(true);
      this.reconnectDelay = 1000;
      if (this.subscriptions.length > 0) {
        this.subscribe(this.subscriptions);
      }
    };

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.status === 'subscribed') return;
        this.onEvent(data);
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.onStatusChange(false);
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws.close();
    };
  }

  subscribe(conflictCodes) {
    this.subscriptions = conflictCodes;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ subscribe: conflictCodes }));
    }
  }

  disconnect() {
    this.closed = true;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  _scheduleReconnect() {
    if (this.closed) return;
    setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
  }
}
