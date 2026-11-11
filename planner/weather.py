"""Weersverwachting via Open-Meteo (gratis, geen sleutel nodig)."""
from __future__ import annotations

import logging
from datetime import date

import requests

log = logging.getLogger(__name__)
URL = "https://api.open-meteo.com/v1/forecast"
MAX_DAGEN = 15
_BFT = [1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]   # km/h-ondergrenzen van Bft 1..12


def bft(kmh: float | None) -> int | None:
    return None if kmh is None else sum(kmh >= t for t in _BFT)


class Weather:
    def __init__(self, session=None):
        self._cache: dict[tuple, dict] = {}
        self._s = session or requests

    def forecast(self, lat: float, lon: float) -> dict[str, dict]:
        key = (round(lat, 2), round(lon, 2))
        if key not in self._cache:
            r = self._s.get(URL, timeout=20, params={
                "latitude": lat, "longitude": lon, "timezone": "Europe/Amsterdam", "forecast_days": 16,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
                         "wind_speed_10m_max,wind_gusts_10m_max,snowfall_sum",
                "hourly": "snow_depth",
            })
            r.raise_for_status()
            self._cache[key] = _parse(r.json())
        return self._cache[key]

    def for_days(self, locatie: dict | None, dagen: list[date]) -> dict[str, dict] | None:
        if not locatie or not dagen or (dagen[0] - date.today()).days > MAX_DAGEN:
            return None
        try:
            fc = self.forecast(locatie["lat"], locatie["lon"])
        except Exception as e:       # weer is mooi meegenomen, maar niet essentieel
            log.warning("Weer ophalen mislukt: %s", e)
            return None
        out = {d.isoformat(): fc[d.isoformat()] for d in dagen if d.isoformat() in fc}
        return out or None


def _parse(j: dict) -> dict[str, dict]:
    d = j["daily"]
    snow = {}
    for t, v in zip(j.get("hourly", {}).get("time", []), j.get("hourly", {}).get("snow_depth", [])):
        if t.endswith("T12:00") and v is not None:
            snow[t[:10]] = round(v * 100)
    out = {}
    for i, dag in enumerate(d["time"]):
        wind = d["wind_speed_10m_max"][i]
        out[dag] = {
            "temp_max": d["temperature_2m_max"][i], "temp_min": d["temperature_2m_min"][i],
            "regen_mm": d["precipitation_sum"][i], "regenkans_pct": d["precipitation_probability_max"][i],
            "wind_kmh": wind, "wind_bft": bft(wind), "windstoten_kmh": d["wind_gusts_10m_max"][i],
            "sneeuwval_cm": d["snowfall_sum"][i], "sneeuwhoogte_cm": snow.get(dag),
        }
    return out


def voldoet(dag: dict, eisen: dict) -> bool:
    def ok(waarde, grens, groter):
        return waarde is not None and (waarde >= grens if groter else waarde <= grens)
    checks = {
        "wind_bft_min": ("wind_bft", True), "wind_bft_max": ("wind_bft", False),
        "temp_min": ("temp_max", True), "temp_max": ("temp_max", False),
        "regen_max_mm": ("regen_mm", False), "sneeuwhoogte_min_cm": ("sneeuwhoogte_cm", True),
    }
    return all(ok(dag.get(veld), grens, groter)
               for eis, grens in eisen.items() if eis in checks
               for veld, groter in [checks[eis]])
