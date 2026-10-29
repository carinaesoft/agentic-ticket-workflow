"""Settings loaded from environment variables.

Every variable is listed in ``.env.example``. The defaults run the whole system locally in
fake LLM mode, without a key and without a ``.env`` file.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Empty values (``OPENAI_API_KEY=``) count as unset, so ``.env.example`` can be copied as is.
    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore")

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "tickets"

    llm_provider: Literal["fake", "openai", "azure"] = "fake"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6-luna"
    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str | None = None

    agent_max_turns: int = Field(default=6, ge=1)
    agent_max_parse_retries: int = Field(default=2, ge=0)

    helpdesk_failure_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    helpdesk_lost_response_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    helpdesk_seed: int | None = None

    log_level: str = "INFO"
