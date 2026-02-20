const API_BASE = import.meta.env.DEV ? 'http://localhost:8080' : '/api';

export const WS_URL = import.meta.env.DEV
  ? 'ws://localhost:8080/ws/live'
  : `ws://${window.location.host}/ws/live`;

async function request(path, params = {}) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value != null) url.searchParams.set(key, value);
  }
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchConflicts(activeOnly = true) {
  return request('/conflicts', { active_only: activeOnly });
}

export async function fetchConflict(conflictId) {
  return request(`/conflicts/${conflictId}`);
}

export async function fetchEvents(conflictId, { since, eventType, limit = 200 } = {}) {
  return request(`/conflicts/${conflictId}/events`, {
    since,
    event_type: eventType,
    limit,
  });
}

export async function fetchMessages(filters = {}) {
  return request('/messages', filters);
}

export async function fetchMessage(messageId) {
  return request(`/messages/${messageId}`);
}

export async function fetchSources(activeOnly = true) {
  return request('/sources', { active_only: activeOnly });
}

export async function fetchHealth() {
  return request('/health');
}
