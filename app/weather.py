"""A one-line weather forecast from Open-Meteo (free, no API key)."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

WMO = {
    0: "clear skies", 1: "mostly clear skies", 2: "partly cloudy skies", 3: "overcast skies",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "passing showers", 81: "showers", 82: "heavy showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def forecast(lat: float, lon: float, city: str, tz: str) -> dict | None:
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon, "timezone": tz, "forecast_days": 1,
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        now = data["current"]
        daily = data["daily"]
        info = {
            "city": city,
            "now": round(now["temperature_2m"]),
            "high": round(daily["temperature_2m_max"][0]),
            "low": round(daily["temperature_2m_min"][0]),
            "code": daily["weather_code"][0],
            "conditions": WMO.get(daily["weather_code"][0], "mixed conditions"),
            "precip": daily.get("precipitation_probability_max", [None])[0],
        }
    except Exception as exc:  # noqa: BLE001 - weather is a nice-to-have
        log.info("Weather unavailable: %s", exc)
        return None
    return info


def spoken(info: dict | None) -> str | None:
    if not info:
        return None

    def deg(v: int) -> str:
        return f"minus {abs(v)}" if v < 0 else str(v)

    line = f"In {info['city']} it's {deg(info['now'])} degrees right now, heading for a high of {deg(info['high'])} with {info['conditions']}."
    if info.get("precip") and info["precip"] >= 50 and info["code"] < 51:
        line += f" There's a {info['precip']} percent chance of rain, so grab an umbrella."
    return line
