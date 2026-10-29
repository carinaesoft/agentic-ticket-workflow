import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.adapters.fake_llm import FakeChatModel
from app.adapters.llm import LLMConfigError
from app.config import Settings
from app.worker import build_activities


def test_worker_wires_settings_into_activities() -> None:
    settings = Settings.model_validate(
        {
            "llm_provider": "fake",
            "helpdesk_failure_rate": 0.0,
            "helpdesk_lost_response_rate": 1.0,
            "helpdesk_seed": 3,
            "agent_max_turns": 4,
        }
    )
    activities = build_activities(settings)
    assert isinstance(activities._model, FakeChatModel)
    assert activities._helpdesk.failure_rate == 0.0
    assert activities._helpdesk.lost_response_rate == 1.0
    assert activities._limits.max_turns == 4


def test_worker_fails_at_startup_without_provider_settings(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigError):
        build_activities(Settings.model_validate({"llm_provider": "openai"}))


def test_worker_without_provider_settings_logs_one_json_error_and_exits() -> None:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("OPENAI_", "AZURE_", "LLM_", "LOG_"))
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.worker"],
        env={**env, "LLM_PROVIDER": "openai"},
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    [line] = result.stdout.splitlines()
    entry = json.loads(line)
    assert (entry["level"], entry["event"]) == ("ERROR", "worker_config_error")
    assert entry["error"] == "LLM_PROVIDER=openai requires OPENAI_API_KEY"


def test_worker_with_invalid_settings_logs_one_json_error_and_exits() -> None:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("OPENAI_", "AZURE_", "LLM_", "LOG_", "HELPDESK_", "AGENT_"))
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.worker"],
        env={**env, "HELPDESK_FAILURE_RATE": "2", "AGENT_MAX_TURNS": "zero"},
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert result.stderr == ""
    [line] = result.stdout.splitlines()
    entry = json.loads(line)
    assert (entry["level"], entry["event"]) == ("ERROR", "worker_config_error")
    assert entry["error"].startswith("invalid settings: ")
    assert "HELPDESK_FAILURE_RATE: Input should be less than or equal to 1" in entry["error"]
    assert "AGENT_MAX_TURNS" in entry["error"]
    assert "zero" not in entry["error"]  # values are not echoed
