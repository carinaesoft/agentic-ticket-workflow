"""Temporal worker entrypoint: ``python -m app.worker``.

Hosts ``TicketWorkflow`` and its activities on the ``tickets`` task queue. It owns the
read-only reference data, the chat model selected by ``LLM_PROVIDER`` and the in-memory
fake Helpdesk. Invalid settings and missing provider settings stop the process at startup
with one JSON error line and exit code 2.
"""

from __future__ import annotations

import asyncio
import logging
import random
import signal
import sys
from datetime import timedelta

from pydantic import ValidationError
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from app.activities import TicketActivities
from app.adapters.helpdesk import FakeHelpdesk
from app.adapters.llm import LLMConfigError, build_chat_model
from app.agent.loop import AgentLimits
from app.config import Settings
from app.data.store import DataStore
from app.logging import configure_logging
from app.workflows.ticket import TicketWorkflow

log = logging.getLogger("app.worker")


def build_activities(settings: Settings) -> TicketActivities:
    return TicketActivities(
        store=DataStore(),
        model=build_chat_model(settings),
        helpdesk=FakeHelpdesk(
            failure_rate=settings.helpdesk_failure_rate,
            lost_response_rate=settings.helpdesk_lost_response_rate,
            rng=random.Random(settings.helpdesk_seed),
        ),
        limits=AgentLimits(
            max_turns=settings.agent_max_turns,
            max_parse_retries=settings.agent_max_parse_retries,
        ),
    )


def build_worker(client: Client, task_queue: str, activities: TicketActivities) -> Worker:
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[TicketWorkflow],
        activities=[
            activities.decide_ticket,
            activities.execute_action,
            activities.lookup_action_result,
        ],
        graceful_shutdown_timeout=timedelta(seconds=10),
    )


async def connect(settings: Settings) -> Client:
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )


CONFIG_ERROR_EXIT_CODE = 2


def settings_error(err: ValidationError) -> str:
    """One readable line naming each invalid variable; input values are left out."""
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']).upper()}: {error['msg']}"
        for error in err.errors(include_input=False, include_url=False)
    )


async def main() -> int:
    try:
        settings = Settings()
    except ValidationError as err:
        configure_logging("INFO")
        log.error(
            "worker_config_error",
            extra={
                "error": f"invalid settings: {settings_error(err)}",
                "hint": "fix the variables (shell or .env); see .env.example",
            },
        )
        return CONFIG_ERROR_EXIT_CODE
    configure_logging(settings.log_level)
    try:
        activities = build_activities(settings)
    except LLMConfigError as err:
        # A configuration problem, not a crash: one clear line instead of a traceback.
        log.error(
            "worker_config_error",
            extra={
                "error": str(err),
                "hint": "set the missing variables (shell or .env) or use LLM_PROVIDER=fake",
            },
        )
        return CONFIG_ERROR_EXIT_CODE
    client = await connect(settings)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with build_worker(client, settings.temporal_task_queue, activities):
        log.info(
            "worker_started",
            extra={
                "task_queue": settings.temporal_task_queue,
                "llm_provider": settings.llm_provider,
                "helpdesk_failure_rate": settings.helpdesk_failure_rate,
                "helpdesk_lost_response_rate": settings.helpdesk_lost_response_rate,
            },
        )
        await stop.wait()
        log.info("worker_stopping")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
