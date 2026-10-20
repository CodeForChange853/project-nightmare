"""Read-only weather lookup via httpx (OpenWeather if key set, Open-Meteo + wttr.in zero-key)."""
from __future__ import annotations

import time
import urllib.parse

import httpx

CACHE_TTL_SEC = 600
_cache: dict[str, tuple[float, str]] = {}

WMO_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    80: "light rain showers",
    81: "moderate rain showers",
    82: "heavy rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "heavy thunderstorm",
}


class WeatherError(RuntimeError):
    pass


async def _fetch_open_meteo(client: httpx.AsyncClient, city: str) -> str:
    geo = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "en", "format": "json"},
    )
    if geo.status_code != 200:
        raise WeatherError(f"Geocoding HTTP {geo.status_code}")
    results = (geo.json() or {}).get("results") or []
    if not results:
        raise WeatherError(f"Could not find location '{city}'")
    loc = results[0]
    lat, lon = loc["latitude"], loc["longitude"]
    resolved_name = loc.get("name") or city

    wx = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code",
        },
    )
    if wx.status_code != 200:
        raise WeatherError(f"Forecast HTTP {wx.status_code}")
    curr = (wx.json() or {}).get("current") or {}
    temp = round(curr.get("temperature_2m", 0))
    feels = round(curr.get("apparent_temperature", temp))
    hum = round(curr.get("relative_humidity_2m", 0))
    code = int(curr.get("weather_code", 0))
    desc = WMO_CODES.get(code, "changeable conditions")
    return f"In {resolved_name} it's {temp}°C (feels like {feels}°C) with {desc}, humidity {hum}%."


async def _fetch_wttr(client: httpx.AsyncClient, city: str) -> str:
    quoted = urllib.parse.quote(city)
    r = await client.get(
        f"https://wttr.in/{quoted}",
        params={"format": "j1"},
        headers={"User-Agent": "ProjectNightmare/1.0"},
    )
    if r.status_code != 200:
        raise WeatherError(f"Weather service returned HTTP {r.status_code}")
    data = r.json()
    curr = (data.get("current_condition") or [{}])[0]
    desc = ((curr.get("weatherDesc") or [{}])[0].get("value") or "clear").lower()
    temp = curr.get("temp_C", "?")
    feels = curr.get("FeelsLikeC", temp)
    hum = curr.get("humidity", "?")
    return f"In {city} it's {temp}°C (feels like {feels}°C) with {desc}, humidity {hum}%."


async def fetch_weather(city: str = "Calbayog", api_key: str = "", timeout: float = 8.0) -> str:
    clean_city = (city or "Calbayog").strip()
    key = clean_city.lower()
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SEC:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if api_key:
                r = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": clean_city, "appid": api_key, "units": "metric"},
                )
                if r.status_code != 200:
                    raise WeatherError(f"OpenWeather returned HTTP {r.status_code}")
                data = r.json()
                desc = (data.get("weather") or [{}])[0].get("description", "clear")
                main = data.get("main") or {}
                temp = round(main.get("temp", 0))
                feels = round(main.get("feels_like", temp))
                hum = main.get("humidity", 0)
                summary = f"In {clean_city} it's {temp}°C (feels like {feels}°C) with {desc}, humidity {hum}%."
            else:
                try:
                    summary = await _fetch_open_meteo(client, clean_city)
                except (httpx.HTTPError, WeatherError, ValueError, KeyError):
                    summary = await _fetch_wttr(client, clean_city)
    except httpx.HTTPError as exc:
        raise WeatherError(f"could not reach weather service: {exc}") from exc
    except (ValueError, KeyError, IndexError) as exc:
        raise WeatherError(f"unexpected weather response: {exc}") from exc

    _cache[key] = (now, summary)
    return summary
