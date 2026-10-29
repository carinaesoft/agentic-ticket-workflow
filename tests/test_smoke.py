import importlib

import pytest

MODULES = [
    "app",
    "app.config",
    "app.logging",
    "app.domain.models",
    "app.domain.rules",
    "app.data.store",
    "app.agent.tools",
    "app.agent.loop",
    "app.agent.prompts",
    "app.adapters.llm",
    "app.adapters.fake_llm",
    "app.adapters.helpdesk",
    "app.activities",
    "app.workflows.ticket",
    "app.api.main",
    "app.api.schemas",
    "app.worker",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    assert importlib.import_module(name) is not None
