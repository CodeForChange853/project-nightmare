"""Read-only weather lookup via httpx (OpenWeather if key set, Open-Meteo + wttr.in zero-key)."""
from __future__ import annotations

from datetime import datetime
import time
import urllib.parse

import httpx

CACHE_TTL_SEC = 3600  # 1 hour cache TTL (updates hourly)
_cache: dict[str, tuple[float, str]] = {}
_card_cache: dict[str, tuple[float, dict]] = {}


def _now_time_label() -> tuple[str, int]:
    now_dt = datetime.now().astimezone()
    return now_dt.strftime("%I:%M %p").lstrip("0"), int(now_dt.timestamp())

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


def _uv_label(uv_val: float | int | None) -> str:
    if uv_val is None:
        return "—"
    uv = round(float(uv_val))
    if uv <= 2:
        lvl = "Low"
    elif uv <= 5:
        lvl = "Mod"
    elif uv <= 7:
        lvl = "High"
    elif uv <= 10:
        lvl = "Very High"
    else:
        lvl = "Extreme"
    return f"{uv} ({lvl})"


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
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,uv_index",
            "daily": "temperature_2m_max,temperature_2m_min,uv_index_max",
            "timezone": "auto",
        },
    )
    if wx.status_code != 200:
        raise WeatherError(f"Forecast HTTP {wx.status_code}")
    wx_json = wx.json() or {}
    curr = wx_json.get("current") or {}
    daily = wx_json.get("daily") or {}
    temp = round(curr.get("temperature_2m", 0))
    feels = round(curr.get("apparent_temperature", temp))
    hum = round(curr.get("relative_humidity_2m", 0))
    code = int(curr.get("weather_code", 0))
    desc = WMO_CODES.get(code, "changeable conditions")
    wind_kmh = curr.get("wind_speed_10m")
    uv_curr = curr.get("uv_index")
    if uv_curr is None:
        uv_max_list = daily.get("uv_index_max") or []
        uv_curr = uv_max_list[0] if uv_max_list else None

    max_list = daily.get("temperature_2m_max") or []
    min_list = daily.get("temperature_2m_min") or []
    high_c = round(max_list[0]) if max_list and max_list[0] is not None else temp
    low_c = round(min_list[0]) if min_list and min_list[0] is not None else temp

    summary = f"In {resolved_name} it's {temp}°C (feels like {feels}°C) with {desc}, humidity {hum}%."
    updated_label, fetched_ts = _now_time_label()
    _card_cache[city.strip().lower()] = (
        time.monotonic(),
        {
            "city": resolved_name,
            "condition": desc.title(),
            "temp_c": temp,
            "feels_c": feels,
            "high_c": high_c,
            "low_c": low_c,
            "humidity": f"{hum}%",
            "wind": f"{round(float(wind_kmh))} km/h" if wind_kmh is not None else "—",
            "uv_index": _uv_label(uv_curr),
            "summary": summary,
            "updated_at": updated_label,
            "fetched_ts": fetched_ts,
            "interval": "1h",
            "live": True,
        },
    )
    return summary


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
    day0 = (data.get("weather") or [{}])[0]
    desc = ((curr.get("weatherDesc") or [{}])[0].get("value") or "clear").lower()
    temp = curr.get("temp_C", "?")
    feels = curr.get("FeelsLikeC", temp)
    hum = curr.get("humidity", "?")
    wind_kmh = curr.get("windspeedKmph")
    uv_val = curr.get("uvIndex") or day0.get("uvIndex")
    high_c = day0.get("maxtempC", temp)
    low_c = day0.get("mintempC", temp)
    summary = f"In {city} it's {temp}°C (feels like {feels}°C) with {desc}, humidity {hum}%."
    try:
        t_int = int(float(temp))
        f_int = int(float(feels))
        h_int = int(float(high_c))
        l_int = int(float(low_c))
        updated_label, fetched_ts = _now_time_label()
        _card_cache[city.strip().lower()] = (
            time.monotonic(),
            {
                "city": city.strip(),
                "condition": desc.title(),
                "temp_c": t_int,
                "feels_c": f_int,
                "high_c": h_int,
                "low_c": l_int,
                "humidity": f"{hum}%",
                "wind": f"{wind_kmh} km/h" if wind_kmh is not None else "—",
                "uv_index": _uv_label(uv_val),
                "summary": summary,
                "updated_at": updated_label,
                "fetched_ts": fetched_ts,
                "interval": "1h",
                "live": True,
            },
        )
    except (ValueError, TypeError):
        pass
    return summary


async def fetch_weather(
    city: str = "Calbayog", api_key: str = "", timeout: float = 8.0, force: bool = False
) -> str:
    clean_city = (city or "Calbayog").strip()
    key = clean_city.lower()
    now = time.monotonic()
    if not force:
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
                wind_obj = data.get("wind") or {}
                temp = round(main.get("temp", 0))
                feels = round(main.get("feels_like", temp))
                high_c = round(main.get("temp_max", temp))
                low_c = round(main.get("temp_min", temp))
                hum = main.get("humidity", 0)
                wind_ms = wind_obj.get("speed")
                wind_kmh = round(float(wind_ms) * 3.6) if wind_ms is not None else None
                summary = f"In {clean_city} it's {temp}°C (feels like {feels}°C) with {desc}, humidity {hum}%."
                updated_label, fetched_ts = _now_time_label()
                _card_cache[key] = (
                    now,
                    {
                        "city": data.get("name") or clean_city,
                        "condition": desc.title(),
                        "temp_c": temp,
                        "feels_c": feels,
                        "high_c": high_c,
                        "low_c": low_c,
                        "humidity": f"{hum}%",
                        "wind": f"{wind_kmh} km/h" if wind_kmh is not None else "—",
                        "uv_index": "—",
                        "summary": summary,
                        "updated_at": updated_label,
                        "fetched_ts": fetched_ts,
                        "interval": "1h",
                        "live": True,
                    },
                )
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


async def prefetch_weather(city: str = "Calbayog", api_key: str = "", timeout: float = 8.0) -> str:
    """Prefetches and warms the weather cache for the given city."""
    return await fetch_weather(city, api_key=api_key, timeout=timeout)


async def run_weather_prefetcher(city: str = "Calbayog", api_key: str = "", interval_sec: int = 3600) -> None:
    """Background worker periodically prefetching weather data on an hourly interval."""
    import asyncio
    while True:
        try:
            await prefetch_weather(city, api_key=api_key)
        except asyncio.CancelledError:
            break
        except Exception:
            pass

        try:
            await asyncio.sleep(interval_sec)
        except asyncio.CancelledError:
            break


def get_cached_weather_card(city: str = "Calbayog") -> dict | None:
    """Returns a structured weather card snapshot from the warm cache in <0.1ms without network calls.
    Returns None if no live weather has been fetched yet (never returns placeholder numbers).
    """
    import re
    clean_city = (city or "Calbayog").strip()
    key = clean_city.lower()
    now = time.monotonic()

    card_entry = _card_cache.get(key)
    if card_entry and now - card_entry[0] < CACHE_TTL_SEC:
        return card_entry[1]

    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SEC:
        summary = cached[1]
        m = re.search(
            r"In\s+(.+?)\s+it's\s+(-?\d+)°C\s+\(feels like\s+(-?\d+)°C\)\s+with\s+(.+?),\s+humidity\s+(\d+)%",
            summary,
            re.IGNORECASE,
        )
        if m:
            resolved_city = m.group(1).strip()
            temp_c = int(m.group(2))
            feels_c = int(m.group(3))
            condition = m.group(4).strip().title()
            humidity = int(m.group(5))
            updated_label, fetched_ts = _now_time_label()
            return {
                "city": resolved_city,
                "condition": condition,
                "temp_c": temp_c,
                "feels_c": feels_c,
                "high_c": temp_c,
                "low_c": temp_c,
                "humidity": f"{humidity}%",
                "wind": "—",
                "uv_index": "—",
                "summary": summary,
                "updated_at": updated_label,
                "fetched_ts": fetched_ts,
                "interval": "1h",
                "live": True,
            }

    return None


async def fetch_weather_card(
    city: str = "Calbayog", api_key: str = "", timeout: float = 8.0, force: bool = False
) -> dict:
    """Fetches live weather if not cached (1h TTL) and returns the real structured weather card."""
    if not force:
        cached_card = get_cached_weather_card(city)
        if cached_card is not None:
            return cached_card
    await fetch_weather(city, api_key=api_key, timeout=timeout, force=force)
    card = get_cached_weather_card(city)
    if card is None:
        raise WeatherError(f"Failed to parse live weather for '{city}'")
    return card


