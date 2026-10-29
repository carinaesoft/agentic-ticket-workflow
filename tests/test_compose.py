"""docker-compose.yml passes every setting through ``${NAME:-default}``, so values from the
shell and from ``.env`` both reach the containers, and the defaults match ``Settings``."""

import re
from pathlib import Path

from app.config import Settings

COMPOSE = Path(__file__).parents[1] / "docker-compose.yml"
INTERPOLATED = re.compile(r"^\s+([A-Z_]+): \$\{([A-Z_]+):-([^}]*)\}$", re.MULTILINE)
SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def compose_settings() -> dict[str, str]:
    entries = {}
    for name, variable, default in INTERPOLATED.findall(COMPOSE.read_text()):
        assert name == variable, f"{name} reads ${{{variable}}}"
        entries[name] = default
    return entries


def test_every_setting_but_the_address_comes_from_the_environment() -> None:
    expected = {name.upper() for name in Settings.model_fields} - {"TEMPORAL_ADDRESS"}
    assert set(compose_settings()) == expected


def test_compose_defaults_match_settings_and_hold_no_secrets(monkeypatch) -> None:
    for name in compose_settings():
        monkeypatch.delenv(name, raising=False)
    defaults = Settings()
    for name, value in compose_settings().items():
        if any(marker in name for marker in SECRET_MARKERS):
            assert value == "", f"{name} must default to empty"
        elif value:
            assert str(getattr(defaults, name.lower())) == value, name
        else:
            assert getattr(defaults, name.lower()) is None, name


def test_tests_service_rebuilds_on_every_run() -> None:
    tests_service = COMPOSE.read_text().split("\n  tests:\n", 1)[1]
    assert "\n    pull_policy: build\n" in tests_service
