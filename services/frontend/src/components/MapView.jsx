import { useEffect, useRef, useMemo } from 'react';
import maplibregl from 'maplibre-gl';
import { useAppContext } from '../context/AppContext';
import { fetchMessage } from '../api/client';
import { eventToFeature, hasValidCoordinates } from '../utils/geo';
import { EVENT_TYPE_COLORS, DEFAULT_EVENT_COLOR } from '../utils/colors';
import { formatTimestamp } from '../utils/time';

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const COUNTRIES_URL = '/data/ne_50m_admin_0_countries.geojson';

const EVENT_COLOR_MATCH = [
  'match',
  ['get', 'event_type'],
  ...Object.entries(EVENT_TYPE_COLORS).flat(),
  DEFAULT_EVENT_COLOR,
];

export default function MapView() {
  const { state, dispatch } = useAppContext();
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const featuresRef = useRef([]);

  const selectedConflict = useMemo(
    () => state.conflicts.find((c) => c.id === state.selectedConflictId),
    [state.conflicts, state.selectedConflictId],
  );

  // Initialize map
  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      center: [30, 30],
      zoom: 2,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      'bottom-right',
    );

    map.on('load', () => {
      // Countries source
      map.addSource('countries', {
        type: 'geojson',
        data: COUNTRIES_URL,
      });

      // Events source
      map.addSource('events', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      // Event dots layer
      map.addLayer({
        id: 'event-dots',
        type: 'circle',
        source: 'events',
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            3, 4,
            8, 7,
            12, 10,
          ],
          'circle-color': EVENT_COLOR_MATCH,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#000000',
          'circle-opacity': [
            'interpolate',
            ['linear'],
            ['get', 'confidence'],
            0.0, 0.4,
            0.5, 0.7,
            1.0, 1.0,
          ],
        },
      });

      // Highlight ring layer
      map.addLayer({
        id: 'event-dots-highlight',
        type: 'circle',
        source: 'events',
        paint: {
          'circle-radius': 14,
          'circle-color': 'transparent',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#FFFFFF',
        },
        filter: ['==', ['get', 'id'], -1],
      });

      // Click handler for event dots
      map.on('click', 'event-dots', (e) => {
        if (!e.features?.length) return;
        const props = e.features[0].properties;
        const eventId = typeof props.id === 'string' ? parseInt(props.id) : props.id;
        dispatch({ type: 'HIGHLIGHT_EVENT', payload: eventId });

        const messageId =
          typeof props.message_id === 'string'
            ? parseInt(props.message_id)
            : props.message_id;

        fetchMessage(messageId)
          .then((msg) => dispatch({ type: 'SET_MESSAGE_DETAIL', payload: msg }))
          .catch(() => {});
      });

      // Click on empty map clears highlight
      map.on('click', (e) => {
        const features = map.queryRenderedFeatures(e.point, {
          layers: ['event-dots'],
        });
        if (!features.length) {
          dispatch({ type: 'CLEAR_HIGHLIGHT' });
        }
      });

      map.on('mouseenter', 'event-dots', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'event-dots', () => {
        map.getCanvas().style.cursor = '';
      });
    });

    mapRef.current = map;

    return () => map.remove();
  }, []);

  // Fly to conflict region + update country layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedConflict) return;

    const onReady = () => {
      map.flyTo({
        center: [selectedConflict.map_center_lon, selectedConflict.map_center_lat],
        zoom: selectedConflict.map_zoom_level,
        duration: 1500,
      });

      updateCountryLayers(map, selectedConflict.color_scheme);
    };

    if (map.isStyleLoaded()) {
      onReady();
    } else {
      map.once('load', onReady);
    }
  }, [selectedConflict]);

  // Update event dots
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const update = () => {
      const source = map.getSource('events');
      if (!source) return;

      const liveFeatures = state.liveEvents
        .map((e) =>
          eventToFeature({
            ...e,
            id: e.event_id,
            latitude: e.lat,
            longitude: e.lon,
            location_name: e.location,
          }),
        )
        .filter(Boolean);

      const liveIds = new Set(state.liveEvents.map((e) => e.event_id));
      const historicalFeatures = state.events
        .filter((e) => !liveIds.has(e.id))
        .map(eventToFeature)
        .filter(Boolean);

      const features = [...liveFeatures, ...historicalFeatures];
      featuresRef.current = features;

      source.setData({
        type: 'FeatureCollection',
        features,
      });
    };

    if (map.isStyleLoaded() && map.getSource('events')) {
      update();
    } else {
      map.once('load', update);
    }
  }, [state.events, state.liveEvents]);

  // Update highlight
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const layer = map.getLayer('event-dots-highlight');
    if (!layer) return;

    if (state.highlightedEventId) {
      map.setFilter('event-dots-highlight', [
        '==',
        ['get', 'id'],
        state.highlightedEventId,
      ]);
    } else {
      map.setFilter('event-dots-highlight', ['==', ['get', 'id'], -1]);
    }
  }, [state.highlightedEventId]);

  // Fly to highlighted event when clicked from feed
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !state.highlightedEventId) return;

    const allEvents = [
      ...state.liveEvents.map((e) => ({
        id: e.event_id,
        lat: e.lat,
        lon: e.lon,
      })),
      ...state.events.map((e) => ({
        id: e.id,
        lat: e.latitude,
        lon: e.longitude,
      })),
    ];

    const target = allEvents.find((e) => e.id === state.highlightedEventId);
    if (target && target.lat != null && target.lon != null && !(target.lat === 0 && target.lon === 0)) {
      map.flyTo({
        center: [target.lon, target.lat],
        zoom: Math.max(map.getZoom(), 8),
        duration: 800,
      });
    }
  }, [state.highlightedEventId]);

  // Show popup for selected message
  useEffect(() => {
    const map = mapRef.current;
    if (popupRef.current) {
      popupRef.current.remove();
      popupRef.current = null;
    }
    if (!map || !state.selectedMessage || !state.highlightedEventId) return;

    const allEvents = [
      ...state.liveEvents.map((e) => ({
        id: e.event_id,
        lat: e.lat,
        lon: e.lon,
        event_type: e.event_type,
        location: e.location,
        confidence: e.confidence,
        timestamp: e.timestamp,
      })),
      ...state.events.map((e) => ({
        id: e.id,
        lat: e.latitude,
        lon: e.longitude,
        event_type: e.event_type,
        location: e.location_name,
        confidence: e.confidence,
        timestamp: e.timestamp,
      })),
    ];

    const event = allEvents.find((e) => e.id === state.highlightedEventId);
    if (!event || !hasValidCoordinates({ latitude: event.lat, longitude: event.lon }))
      return;

    const msg = state.selectedMessage;
    const popup = new maplibregl.Popup({
      closeOnClick: true,
      maxWidth: '340px',
      className: 'event-popup',
    })
      .setLngLat([event.lon, event.lat])
      .setHTML(
        `<div class="popup-content">
          <div class="popup-header">
            <span class="popup-time">${formatTimestamp(event.timestamp)}</span>
            <span class="popup-type">${event.event_type || 'unknown'}</span>
          </div>
          <div class="popup-source">
            ${msg.source_display_name || msg.source_identifier || 'Unknown'}
            <span class="popup-platform">${msg.platform}</span>
            ${msg.reliability_tier ? `<span class="popup-tier">${msg.reliability_tier}</span>` : ''}
          </div>
          <div class="popup-text">${escapeHtml(msg.text?.slice(0, 300) || '')}${(msg.text?.length || 0) > 300 ? '...' : ''}</div>
          ${event.location ? `<div class="popup-location">${escapeHtml(event.location)}</div>` : ''}
          ${event.confidence != null ? `<div class="popup-confidence">Confidence: ${(event.confidence * 100).toFixed(0)}%</div>` : ''}
        </div>`,
      )
      .addTo(map);

    popup.on('close', () => {
      popupRef.current = null;
    });

    popupRef.current = popup;
  }, [state.selectedMessage, state.highlightedEventId]);

  return <div ref={containerRef} className="map-container" />;
}

function updateCountryLayers(map, colorScheme) {
  if (!colorScheme) return;

  const groups = ['allies', 'adversaries', 'involved'];

  // Remove existing country layers
  for (const group of groups) {
    if (map.getLayer(`country-${group}-fill`)) map.removeLayer(`country-${group}-fill`);
    if (map.getLayer(`country-${group}-line`)) map.removeLayer(`country-${group}-line`);
  }

  // Add layers for each group, below event dots
  for (const group of groups) {
    const config = colorScheme[group];
    if (!config || !config.countries?.length) continue;

    const filter = [
      'any',
      ['in', ['get', 'ISO_A2'], ['literal', config.countries]],
      ['in', ['get', 'ISO_A2_EH'], ['literal', config.countries]],
    ];

    map.addLayer(
      {
        id: `country-${group}-fill`,
        type: 'fill',
        source: 'countries',
        paint: {
          'fill-color': config.color,
          'fill-opacity': 0.2,
        },
        filter,
      },
      'event-dots',
    );

    map.addLayer(
      {
        id: `country-${group}-line`,
        type: 'line',
        source: 'countries',
        paint: {
          'line-color': config.color,
          'line-width': 1.5,
          'line-opacity': 0.7,
        },
        filter,
      },
      'event-dots',
    );
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
