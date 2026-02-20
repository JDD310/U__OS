export function getCountryCode(feature) {
  const code = feature.properties.ISO_A2;
  return code === '-99' ? feature.properties.ISO_A2_EH : code;
}

export function hasValidCoordinates(event) {
  const lat = event.latitude ?? event.lat;
  const lon = event.longitude ?? event.lon;
  return lat != null && lon != null && !(lat === 0 && lon === 0);
}

export function eventToFeature(event) {
  const lat = event.latitude ?? event.lat;
  const lon = event.longitude ?? event.lon;
  if (!hasValidCoordinates(event)) return null;

  return {
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: [lon, lat],
    },
    properties: {
      id: event.id ?? event.event_id,
      message_id: event.message_id,
      event_type: event.event_type || 'unknown',
      location_name: event.location_name ?? event.location ?? '',
      confidence: event.confidence ?? 0.5,
      timestamp: event.timestamp,
      text: event.text ?? '',
    },
  };
}
