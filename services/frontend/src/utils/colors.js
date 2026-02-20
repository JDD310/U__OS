export const EVENT_TYPE_COLORS = {
  airstrike: '#FF1744',
  missile_strike: '#FF1744',
  shelling: '#FF6D00',
  interception: '#448AFF',
  casualty_report: '#B71C1C',
  movement: '#FFAB00',
  diplomatic: '#69F0AE',
  arms_transfer: '#7C4DFF',
  statement: '#78909C',
};

export const DEFAULT_EVENT_COLOR = '#FFFFFF';

export function getEventColor(eventType) {
  return EVENT_TYPE_COLORS[eventType] || DEFAULT_EVENT_COLOR;
}
