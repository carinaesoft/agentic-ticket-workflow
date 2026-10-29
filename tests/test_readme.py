"""The README keeps the sections the project documents promise."""

from pathlib import Path

README = (Path(__file__).resolve().parent.parent / "README.md").read_text()

REQUIRED_HEADINGS = [
    "## Quick start",
    "## Running the tests",
    "## Example requests",
    "## Architecture",
    "## Workflow or activity: where each piece runs",
    "## Retries, timeouts and duplicates",
    "## How the rules are protected from ticket content",
    "## Configuration",
    "## Deploying on Azure",
    "## How AI coding assistants were used",
    "## Assumptions, limitations and next steps",
]


def test_readme_has_every_required_heading_in_order():
    lines = README.splitlines()
    positions = [lines.index(heading) for heading in REQUIRED_HEADINGS]
    assert positions == sorted(positions)


def test_readme_has_a_mermaid_diagram():
    assert "```mermaid" in README


def test_ai_assistant_section_is_still_a_skeleton():
    section = README.split("## How AI coding assistants were used")[1]
    section = section.split("\n## ")[0]
    assert "TODO" in section
