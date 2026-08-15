"""Live weather for the dashboard header — Open-Meteo, chosen specifically
because it needs no API key/signup, so this works out of the box in every
environment without provisioning a secret. Geocodes the employee's free-text
`location` field, then reads current conditions for those coordinates.
Failures (no location set, geocoding miss, network error) all degrade to
`None` — the frontend simply omits the weather chip rather than erroring."""

import time

import requests

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
WEATHER_URL = 'https://api.open-meteo.com/v1/forecast'
REQUEST_TIMEOUT = 4
CACHE_TTL_SECONDS = 3 * 60 * 60  # weather/geocoding barely change hour to hour

_cache: dict[str, tuple[float, dict | None]] = {}


def _cached(key, compute):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    value = compute()
    _cache[key] = (now, value)
    return value


def _geocode(location: str):
    def compute():
        try:
            resp = requests.get(GEOCODE_URL, params={'name': location, 'count': 1}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get('results') or []
        except requests.RequestException:
            return None
        if not results:
            return None
        top = results[0]
        return {'lat': top['latitude'], 'lon': top['longitude'], 'label': top.get('name', location)}

    return _cached(f'geocode:{location.lower()}', compute)


def get_weather_for_location(location: str):
    """Returns {'temperature_f': float, 'location': str} or None."""
    if not location:
        return None
    place = _geocode(location)
    if not place:
        return None

    def compute():
        try:
            resp = requests.get(
                WEATHER_URL,
                params={
                    'latitude': place['lat'], 'longitude': place['lon'],
                    'current': 'temperature_2m', 'temperature_unit': 'fahrenheit',
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            current = resp.json().get('current') or {}
            temp = current.get('temperature_2m')
        except requests.RequestException:
            return None
        if temp is None:
            return None
        return {'temperature_f': temp, 'location': place['label']}

    return _cached(f'weather:{place["lat"]}:{place["lon"]}', compute)
