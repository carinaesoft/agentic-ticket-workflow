import json
import logging
import sys

import pytest

from app.config import Settings
from app.logging import JsonFormatter, configure_logging, ticket_extra, workflow_id_for

ENV_NAMES = [
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "HELPDESK_SEED",
    "TEMPORAL_ADDRESS",
    "AGENT_MAX_TURNS",
]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_defaults_give_fake_mode(clean_env) -> None:
    settings = Settings()
    assert settings.llm_provider == "fake"
    assert settings.temporal_address == "localhost:7233"
    assert settings.temporal_task_queue == "tickets"
    assert settings.agent_max_turns == 6
    assert settings.agent_max_parse_retries == 2
    assert settings.helpdesk_failure_rate == 0.2
    assert settings.helpdesk_lost_response_rate == 0.1
    assert settings.helpdesk_seed is None
    assert settings.openai_api_key is None


def test_env_overrides_and_empty_values_count_as_unset(clean_env) -> None:
    clean_env.setenv("LLM_PROVIDER", "openai")
    clean_env.setenv("OPENAI_API_KEY", "")
    clean_env.setenv("HELPDESK_SEED", "")
    clean_env.setenv("AGENT_MAX_TURNS", "3")
    settings = Settings()
    assert settings.llm_provider == "openai"
    assert settings.openai_api_key is None
    assert settings.helpdesk_seed is None
    assert settings.agent_max_turns == 3


def test_secret_is_not_printed(clean_env) -> None:
    clean_env.setenv("OPENAI_API_KEY", "sk-test-value")
    assert "sk-test-value" not in repr(Settings())


def make_record(**extra) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "test", "levelname": "INFO", "msg": "hello %s"})
    record.args = ("world",)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_one_json_object_with_ids() -> None:
    line = JsonFormatter().format(make_record(**ticket_extra("T-1"), tool="search_kb"))
    assert "\n" not in line
    entry = json.loads(line)
    assert entry["event"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["ticket_id"] == "T-1"
    assert entry["workflow_id"] == "ticket-T-1"
    assert entry["tool"] == "search_kb"
    assert entry["ts"].endswith("+00:00")


def test_formatter_lifts_workflow_id_from_temporal_extra() -> None:
    record = make_record(
        ticket_id="T-2",
        temporal_workflow={"workflow_id": "ticket-T-2", "run_id": "r", "workflow_type": "W"},
    )
    entry = json.loads(JsonFormatter().format(record))
    assert entry["workflow_id"] == "ticket-T-2"
    assert "temporal_workflow" not in entry


def test_formatter_lifts_activity_attempt() -> None:
    record = make_record(
        ticket_id="T-2",
        temporal_activity={
            "workflow_id": "ticket-T-2",
            "activity_type": "execute_action",
            "attempt": 3,
        },
    )
    entry = json.loads(JsonFormatter().format(record))
    assert entry["workflow_id"] == "ticket-T-2"
    assert entry["attempt"] == 3
    assert entry["activity"] == "execute_action"


def test_formatter_derives_ticket_id_from_workflow_id() -> None:
    record = make_record(temporal_activity={"workflow_id": "ticket-T-5", "attempt": 2})
    entry = json.loads(JsonFormatter().format(record))
    assert (entry["ticket_id"], entry["workflow_id"]) == ("T-5", "ticket-T-5")
    assert json.loads(JsonFormatter().format(make_record()))["ticket_id"] is None


def test_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record()
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["exc"]


def test_workflow_id_is_deterministic() -> None:
    assert workflow_id_for("T-7") == "ticket-T-7"


def test_configure_logging_installs_json_handler(capsys) -> None:
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    try:
        configure_logging("debug")
        logging.getLogger("app.test").info("ticket_received", extra=ticket_extra("T-1"))
        entry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert entry["event"] == "ticket_received"
        assert entry["workflow_id"] == "ticket-T-1"
    finally:
        root.handlers, root.level = previous_handlers, previous_level
