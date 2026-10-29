from pathlib import Path

from app.config import Settings

ENV_EXAMPLE = Path(__file__).parents[1] / ".env.example"
SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def env_example() -> dict[str, str]:
    entries = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            entries[name] = value
    return entries


def test_every_setting_is_documented() -> None:
    documented = set(env_example())
    expected = {name.upper() for name in Settings.model_fields}
    assert expected == documented


def test_no_secret_values() -> None:
    for name, value in env_example().items():
        if any(marker in name for marker in SECRET_MARKERS):
            assert value == "", f"{name} must be empty in .env.example"


def test_documented_defaults_match_settings(monkeypatch) -> None:
    for name in env_example():
        monkeypatch.delenv(name, raising=False)
    defaults = Settings()
    for name, value in env_example().items():
        if value:
            assert str(getattr(defaults, name.lower())) == value, name
