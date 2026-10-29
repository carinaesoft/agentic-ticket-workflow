"""JSON-lines logging configuration.

One JSON object per line on stdout: ``ts, level, logger, event, ticket_id, workflow_id`` and
any extra fields. ``workflow_id`` (and ``attempt`` for activities) is lifted from the
``temporal_workflow`` / ``temporal_activity`` extras the Temporal SDK attaches to records
from ``workflow.logger`` and ``activity.logger``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else on a record is an ``extra`` field.
# ``color_message`` is uvicorn's ANSI-coloured duplicate of the message.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}
_TEMPORAL_EXTRAS = ("temporal_workflow", "temporal_activity")
_WORKFLOW_PREFIX = "ticket-"


def workflow_id_for(ticket_id: str) -> str:
    """The deterministic workflow ID of a ticket."""
    return f"{_WORKFLOW_PREFIX}{ticket_id}"


def ticket_extra(ticket_id: str, workflow_id: str | None = None, **fields: Any) -> dict[str, Any]:
    """``extra=`` mapping binding a log line to a ticket and its workflow."""
    return {
        "ticket_id": ticket_id,
        "workflow_id": workflow_id or workflow_id_for(ticket_id),
        **fields,
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "ticket_id": getattr(record, "ticket_id", None),
            "workflow_id": getattr(record, "workflow_id", None),
        }
        for key in _TEMPORAL_EXTRAS:
            info = getattr(record, key, None)
            if isinstance(info, dict):
                entry["workflow_id"] = entry["workflow_id"] or info.get("workflow_id")
                if "attempt" in info and key == "temporal_activity":
                    entry["attempt"] = info["attempt"]
                if "activity_type" in info:
                    entry["activity"] = info["activity_type"]
        workflow_id = entry["workflow_id"]
        if entry["ticket_id"] is None and str(workflow_id).startswith(_WORKFLOW_PREFIX):
            # Workflow IDs are ``ticket-{ticket_id}``, so SDK log lines about a ticket's
            # workflow (e.g. activity retries) still name the ticket.
            entry["ticket_id"] = workflow_id.removeprefix(_WORKFLOW_PREFIX)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key not in _TEMPORAL_EXTRAS and key not in entry:
                entry[key] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Route every logger (including uvicorn's) through one JSON handler on stdout."""
    from temporalio import activity, workflow

    # The Temporal context already arrives as structured extras; keep ``event`` clean.
    workflow.logger.workflow_info_on_message = False
    activity.logger.activity_info_on_message = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
