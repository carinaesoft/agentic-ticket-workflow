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
