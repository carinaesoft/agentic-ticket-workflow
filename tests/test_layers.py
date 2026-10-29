"""Import boundaries: the API process must not load the LLM SDK or the activities."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def loaded_modules(module: str) -> set[str]:
    """Modules in ``sys.modules`` after importing ``module`` in a fresh interpreter."""
    code = f"import json, sys; import {module}; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return set(json.loads(out.stdout))


def test_api_does_not_load_the_llm_sdk_or_the_activities() -> None:
    modules = loaded_modules("app.api.main")
    assert "openai" not in modules
    assert not {m for m in modules if m == "app.activities" or m.startswith("app.adapters")}
    assert not {m for m in modules if m.startswith("app.agent")}


def test_workflow_does_not_import_the_activities() -> None:
    tree = ast.parse((ROOT / "app" / "workflows" / "ticket.py").read_text())
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not {m for m in imported if m and m.startswith(("app.activities", "app.adapters"))}
    assert "openai" not in loaded_modules("app.workflows.ticket")
