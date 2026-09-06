"""Weather adapter — Open-Meteo → the core's `WeatherData` (DESIGN §2.2, §2.6, §3.1).

Open-Meteo needs no account or API key (DESIGN §2.2), so there is nothing to
rotate or leak on the home box. This module is the world-facing side: it makes one
HTTP request and parses the reply into the core's plain `WeatherData` shape. It
reads no clock and makes no display decisions — hourly times come back tz-aware in
UTC and the core (`assemble._weather_hours`) localizes them to Europe/Warsaw and
trims the strip to the rest of today.

`now` is part of the adapter interface for symmetry with the other adapters, but is
deliberately unused: trimming the hourly strip against the current time is the
core's job (DESIGN §3.1), so the adapter just returns the whole fetched series.

Failure, never an exception (DESIGN §2.6): a network error, a non-200 status, or a
body missing the fields we need each return a `Failure` marker, so the refresh loop
never has to catch anything and `assemble` marks the region "niedostępne".
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from trmnl.core.model import Failure, HourPoint, WeatherData

# Open-Meteo's free forecast endpoint. No key, no account (DESIGN §2.2).
_URL = "https://api.open-meteo.com/v1/forecast"

# One slow source must not delay the whole image (DESIGN §2.6), so every fetch is
# bounded. Set on the call so the guarantee holds whatever client is injected.
_TIMEOUT_S = 10.0

# What we ask for. `timezone=GMT` makes every returned timestamp UTC (the API emits
# naive ISO strings plus utc_offset_seconds=0); we attach UTC tzinfo and leave the
# UTC→Europe/Warsaw conversion to the core. Units are pinned metric explicitly so a
# change to Open-Meteo's defaults can never silently switch them (DESIGN §2.2).
# is_day (1 by day, 0 at night) lets the core show a moon instead of a sun for a
# clear sky after dark (DESIGN §2.2, T11). It costs nothing extra — same request.
_CURRENT = "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day"
# weather_code per hour drives the hourly strip's icons (the core maps it to an
# icon key, same as the current conditions); temperature and precip stay too.
# is_day is per-hour so each strip column can show a moon or a sun on its own.
_HOURLY = "temperature_2m,precipitation_probability,weather_code,is_day"

# Two days of hourly data guarantees the whole of today's Europe/Warsaw calendar
# day is covered whichever side of a UTC day boundary "now" falls; the core keeps
# only the rest of today and caps it, so the surplus is cheap and never drawn.
_FORECAST_DAYS = 2


def fetch_weather(
    lat: float, lon: float, now: datetime, client: httpx.Client
) -> WeatherData | Failure:
    """Fetch current conditions plus today's hourly strip for `lat`/`lon`.

    Returns `WeatherData` on a well-formed 200, or `Failure` on any network error,
    non-200 status, or body missing the fields we need — never raising into the
    caller (DESIGN §2.6). `now` is accepted for interface symmetry and unused (see
    the module docstring); `client` is an injected `httpx.Client` so tests stub it
    and hit no network."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": _CURRENT,
        "hourly": _HOURLY,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "timezone": "GMT",
        "forecast_days": _FORECAST_DAYS,
    }
    try:
        resp = client.get(_URL, params=params, timeout=_TIMEOUT_S)
    except httpx.HTTPError as exc:
        return Failure(f"weather: request failed: {exc}")

    if resp.status_code != 200:
        return Failure(f"weather: HTTP {resp.status_code}")

    try:
        return _parse(resp.json())
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        # ValueError also covers json() on a non-JSON body (JSONDecodeError) and
        # round()/int() on a non-number; a half-filled WeatherData is never returned.
        return Failure(f"weather: unparseable body: {exc}")


def _is_day(value) -> bool:
    """Open-Meteo's is_day flag (1 by day, 0 at night) as a bool. A null or absent
    value is treated as day — draw the sun — the safe fallback (DESIGN §2.2, §2.6),
    never a `Failure`. The same spirit as a null weather code falling back to the
    neutral cloud: the day/night flag is cosmetic, so it never fails a fetch."""
    return True if value is None else int(value) == 1


def _parse(payload: dict) -> WeatherData:
    """Turn a decoded Open-Meteo response into `WeatherData`. Any missing key,
    misaligned array, or non-numeric value raises (KeyError/TypeError/ValueError)
    and is turned into `Failure` by the caller, so this never returns a partial
    object."""
    current = payload["current"]
    hourly = payload["hourly"]

    times = hourly["time"]
    temps = hourly["temperature_2m"]
    probs = hourly["precipitation_probability"]
    codes = hourly["weather_code"]
    # is_day is read leniently: a wholly-absent array (or a null in it) falls back
    # to day per hour rather than failing the fetch, so an older cached response
    # that predates this field still renders (DESIGN §2.6). The required arrays
    # above still drive the length check.
    days = hourly.get("is_day", [])

    points: list[HourPoint] = []
    # Mismatched array lengths are a malformed body, not a silent truncation.
    # zip(strict=True) would catch that, but it is Python 3.10+ and the deploy Pi
    # runs 3.9 (DESIGN §5), so check the lengths explicitly and then plain-zip.
    # Open-Meteo returns these arrays index-aligned.
    if not (len(times) == len(temps) == len(probs) == len(codes)):
        raise ValueError("hourly arrays have mismatched lengths")
    for i, (iso, temp, prob, code) in enumerate(zip(times, temps, probs, codes)):
        when = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
        # Index defensively: a short or absent is_day array leaves later hours as
        # day rather than raising, matching the null → day fallback above.
        day_flag = days[i] if i < len(days) else None
        # precipitation_probability is legitimately null for hours past the model's
        # probability horizon; those hours are never today, so a missing chance
        # reads as 0% rather than failing the whole fetch. A null temperature, by
        # contrast, is malformed and raises via round(None).
        # A null weather_code (unusual — it is a core variable) degrades only that
        # hour's icon to the neutral fallback rather than failing the fetch: -1 is
        # not in the core's code map, so it maps to the fallback cloud.
        points.append(
            HourPoint(
                time=when,
                temp_c=round(temp),
                rain_pct=round(prob or 0),
                code=int(code) if code is not None else -1,
                is_day=_is_day(day_flag),
            )
        )

    return WeatherData(
        temp_c=round(current["temperature_2m"]),
        condition_code=int(current["weather_code"]),
        feels_like_c=round(current["apparent_temperature"]),
        wind_kmh=round(current["wind_speed_10m"]),
        is_day=_is_day(current.get("is_day")),
        hourly=points,
    )
