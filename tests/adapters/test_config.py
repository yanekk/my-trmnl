"""Config loader tests (DESIGN §3.5, §5, task T08). A person writes this file by
hand, so every field is validated on load and a bad one fails with a message that
names it — not a KeyError deep inside a fetch. The committed config.example.toml is
loaded here too, so it can never drift into being invalid.
"""

import os
from datetime import time
from pathlib import Path

import pytest

from trmnl.adapters.config import Config, ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO_ROOT / "config.example.toml"

_VALID = """
[location]
lat = 54.372
lon = 18.638
place = "Gdańsk"

[buses]
stops = ["Hynka"]
line = "227"
stops_label = "Hynka"
near_minutes = 15

[calendar]
ids = ["cal@example.com"]
token_path = "~/.config/trmnl/token.json"

[service]
start = "05:00"
end = "23:00"

[server]
image_path = "/var/lib/trmnl/screen.bmp"
host = "0.0.0.0"
port = 8080
"""


def _write(tmp_path, text) -> str:
    p = tmp_path / "config.toml"
    p.write_text(text)
    return str(p)


def test_valid_config_loads_into_a_config(tmp_path):
    cfg = load_config(_write(tmp_path, _VALID))
    assert isinstance(cfg, Config)
    assert (cfg.lat, cfg.lon, cfg.place) == (54.372, 18.638, "Gdańsk")
    assert cfg.stops == ["Hynka"]
    assert cfg.line == "227"
    assert cfg.stops_label == "Hynka"
    assert cfg.near_minutes == 15
    assert cfg.calendar_ids == ["cal@example.com"]
    assert cfg.service_start == time(5, 0)
    assert cfg.service_end == time(23, 0)
    assert cfg.image_path == "/var/lib/trmnl/screen.bmp"
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8080


def test_committed_example_config_is_valid():
    # The example ships in the repo; a broken example is worse than none.
    cfg = load_config(EXAMPLE)
    assert isinstance(cfg, Config)
    assert cfg.place == "Gdańsk"


def test_home_relative_token_path_is_expanded(tmp_path):
    cfg = load_config(_write(tmp_path, _VALID))
    assert cfg.token_path == os.path.expanduser("~/.config/trmnl/token.json")
    assert "~" not in cfg.token_path


def test_startup_path_defaults_to_the_committed_placeholder(tmp_path):
    cfg = load_config(_write(tmp_path, _VALID))
    assert cfg.startup_path.endswith(os.path.join("render", "startup.bmp"))
    assert os.path.exists(cfg.startup_path)


def test_near_minutes_defaults_when_absent(tmp_path):
    text = _VALID.replace("near_minutes = 15\n", "")
    cfg = load_config(_write(tmp_path, text))
    assert cfg.near_minutes == 15


def test_line_written_as_a_bare_number_is_accepted(tmp_path):
    text = _VALID.replace('line = "227"', "line = 227")
    cfg = load_config(_write(tmp_path, text))
    assert cfg.line == "227"


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(str(tmp_path / "does-not-exist.toml"))


def test_invalid_toml_is_a_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(_write(tmp_path, "this is = = not toml"))


def test_missing_section_names_the_section(tmp_path):
    text = _VALID.replace("[calendar]\nids", "[calendarr]\nids")
    with pytest.raises(ConfigError, match=r"\[calendar\]"):
        load_config(_write(tmp_path, text))


def test_missing_required_field_names_it(tmp_path):
    text = _VALID.replace('place = "Gdańsk"\n', "")
    with pytest.raises(ConfigError, match=r"\[location\].place"):
        load_config(_write(tmp_path, text))


def test_out_of_range_coordinate_is_rejected(tmp_path):
    text = _VALID.replace("lat = 54.372", "lat = 200.0")
    with pytest.raises(ConfigError, match="out of range"):
        load_config(_write(tmp_path, text))


def test_non_numeric_coordinate_is_rejected(tmp_path):
    text = _VALID.replace("lat = 54.372", 'lat = "north"')
    with pytest.raises(ConfigError, match=r"\[location\].lat"):
        load_config(_write(tmp_path, text))


def test_empty_stops_list_is_rejected(tmp_path):
    text = _VALID.replace('stops = ["Hynka"]', "stops = []")
    with pytest.raises(ConfigError, match=r"\[buses\].stops"):
        load_config(_write(tmp_path, text))


def test_empty_calendar_ids_is_rejected(tmp_path):
    text = _VALID.replace('ids = ["cal@example.com"]', "ids = []")
    with pytest.raises(ConfigError, match=r"\[calendar\].ids"):
        load_config(_write(tmp_path, text))


def test_service_hours_must_be_whole_hours(tmp_path):
    text = _VALID.replace('start = "05:00"', 'start = "05:30"')
    with pytest.raises(ConfigError, match="whole hour"):
        load_config(_write(tmp_path, text))


def test_service_end_before_start_is_rejected(tmp_path):
    text = _VALID.replace('end = "23:00"', 'end = "04:00"')
    with pytest.raises(ConfigError, match="before end"):
        load_config(_write(tmp_path, text))


def test_bad_time_string_is_rejected(tmp_path):
    text = _VALID.replace('start = "05:00"', 'start = "notatime"')
    with pytest.raises(ConfigError, match="not a valid"):
        load_config(_write(tmp_path, text))
