"""Config file for the composition root (DESIGN §3.5, §5, task T08).

Everything that varies between one household and the next — the coordinates, the
stops, the line, the calendar ids, the service window, where the image is written
— lives in one TOML file on the box, not in the code. This module reads it,
validates it, and hands the composition root (`server/loop.py`) a frozen `Config`.

**Why TOML and the standard library.** Python 3.12 ships `tomllib`, so reading the
file adds no dependency to pin on the box (DESIGN §5's dependency policy). The file
is written by a person, so every field is validated on load with a message that
names the field and section, rather than failing deep inside a fetch with a
`KeyError` (task T08: "Config is validated on load with clear errors").

**What is not here.** The OAuth refresh token is a separate file, stored 0o600 by
`google_auth` and never in this config — this file only carries its *path*
(DESIGN §3.5). The real config with the owner's private coordinates and calendar
id is created at deploy (T09) and is git-ignored; `config.example.toml` documents
the shape and ships in the repo.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path


class ConfigError(Exception):
    """A config file that is missing, unreadable, or has a bad/absent field. The
    message names the field so the person editing the file can fix it; the
    composition root prints it and exits rather than starting half-configured."""


@dataclass(frozen=True)
class Config:
    """The validated configuration the composition root runs on. Coordinates and
    calendar ids are private to the household and never leave the box (DESIGN §1);
    this object only holds them in memory for the fetch cycle."""

    lat: float
    lon: float
    stops: list[str]
    line: str
    near_minutes: int
    calendar_ids: list[str]
    token_path: str  # the OAuth refresh-token file (google_auth), 0o600 on the box
    service_start: time  # Europe/Warsaw; drives the refresh policy (whole hours)
    service_end: time
    image_path: str  # where the refresh loop writes the served BMP (atomic rename)
    startup_path: str  # the committed cold-start placeholder BMP the server falls back to
    place: str  # weather heading suffix, e.g. "Gdańsk"
    stops_label: str  # buses heading suffix, e.g. "Hynka"
    host: str  # server bind address (LAN-only seatbelt is a deploy property, DESIGN §5.2)
    port: int


# The committed placeholder lives beside the renderer (DESIGN §2.6, §3.5); the
# server serves it until the first real image exists. Used as the default when the
# config omits an explicit path.
_DEFAULT_STARTUP_PATH = str(Path(__file__).resolve().parent.parent / "render" / "startup.bmp")


def load_config(path: str | Path) -> Config:
    """Read and validate the TOML config at `path`, or raise `ConfigError`.

    Every field is checked here so a bad file fails at startup with a clear message
    rather than midway through a fetch. Paths starting with `~` are expanded so the
    token can live under the deploy user's home. Service hours are whole hours in
    Europe/Warsaw and must not cross midnight, matching the refresh policy's window
    (`core/refresh.py`, which keys on the hour)."""
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except OSError as exc:
        raise ConfigError(f"config: cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config: {path} is not valid TOML: {exc}") from exc

    location = _section(raw, "location")
    buses = _section(raw, "buses")
    calendar = _section(raw, "calendar")
    service = _section(raw, "service")
    server = _section(raw, "server")

    lat = _coordinate(location, "location", "lat", -90.0, 90.0)
    lon = _coordinate(location, "location", "lon", -180.0, 180.0)
    place = _nonempty_str(location, "location", "place")

    stops = _str_list(buses, "buses", "stops")
    line = _nonempty_str(buses, "buses", "line", coerce_number=True)
    stops_label = _nonempty_str(buses, "buses", "stops_label")
    near_minutes = _positive_int(buses, "buses", "near_minutes", default=15)

    calendar_ids = _str_list(calendar, "calendar", "ids")
    token_path = _expand(_nonempty_str(calendar, "calendar", "token_path"))

    service_start = _hour(service, "service", "start")
    service_end = _hour(service, "service", "end")
    if service_start >= service_end:
        raise ConfigError(
            "config: [service] start must be before end and not cross midnight "
            f"(got start={service_start:%H:%M}, end={service_end:%H:%M})"
        )

    image_path = _expand(_nonempty_str(server, "server", "image_path"))
    startup_path = _expand(
        server.get("startup_path") or _DEFAULT_STARTUP_PATH
    )
    host = server.get("host", "0.0.0.0")
    port = _positive_int(server, "server", "port", default=8080)

    return Config(
        lat=lat,
        lon=lon,
        stops=stops,
        line=line,
        near_minutes=near_minutes,
        calendar_ids=calendar_ids,
        token_path=token_path,
        service_start=service_start,
        service_end=service_end,
        image_path=image_path,
        startup_path=startup_path,
        place=place,
        stops_label=stops_label,
        host=host,
        port=port,
    )


# --- field validators -------------------------------------------------------
# Each raises ConfigError naming the [section] and key, so a person editing the
# file learns exactly what to fix.


def _section(raw: dict, name: str) -> dict:
    value = raw.get(name)
    if value is None:
        raise ConfigError(f"config: missing required section [{name}]")
    if not isinstance(value, dict):
        raise ConfigError(f"config: [{name}] must be a table")
    return value


def _coordinate(section: dict, sname: str, key: str, lo: float, hi: float) -> float:
    value = _required(section, sname, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"config: [{sname}].{key} must be a number")
    value = float(value)
    if not lo <= value <= hi:
        raise ConfigError(f"config: [{sname}].{key}={value} is out of range [{lo}, {hi}]")
    return value


def _nonempty_str(section: dict, sname: str, key: str, *, coerce_number: bool = False) -> str:
    value = _required(section, sname, key)
    # A line like 227 is naturally written unquoted in TOML; accept an int there
    # and stringify it, but never a bool (TOML has no bare number that is a bool).
    if coerce_number and isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"config: [{sname}].{key} must be a non-empty string")
    return value


def _str_list(section: dict, sname: str, key: str) -> list[str]:
    value = _required(section, sname, key)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"config: [{sname}].{key} must be a non-empty list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"config: [{sname}].{key} must contain only non-empty strings")
        out.append(item)
    return out


def _positive_int(section: dict, sname: str, key: str, *, default: int) -> int:
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"config: [{sname}].{key} must be a positive integer")
    return value


def _hour(section: dict, sname: str, key: str) -> time:
    """Parse "HH:MM" into a `time`, requiring a whole hour. The refresh policy
    (`core/refresh.py`) keys on the hour only, so a non-zero minute would be
    silently ignored — rejecting it here makes that a clear error, not a surprise."""
    value = _required(section, sname, key)
    if not isinstance(value, str):
        raise ConfigError(f"config: [{sname}].{key} must be a \"HH:MM\" string")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"config: [{sname}].{key}={value!r} is not a valid HH:MM time") from exc
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ConfigError(
            f"config: [{sname}].{key}={value!r} must be a whole hour "
            "(the refresh policy keys on the hour; minutes are not supported)"
        )
    return parsed


def _required(section: dict, sname: str, key: str):
    if key not in section:
        raise ConfigError(f"config: [{sname}].{key} is required")
    return section[key]


def _expand(path: str) -> str:
    """Expand a leading `~` so a path like ~/.config/trmnl/token.json resolves to
    the deploy user's home. A path with no `~` is returned unchanged."""
    return str(Path(path).expanduser())
