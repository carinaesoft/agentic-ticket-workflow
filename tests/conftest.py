import os
from collections.abc import AsyncIterator

import pytest_asyncio
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

# The time-skipping test server binary is downloaded here once and reused afterwards, so
# the suite runs offline from the second run on (the tests image caches it at build time).
TEST_SERVER_DIR = os.environ.get("TEMPORAL_TEST_SERVER_DIR", ".temporal-test-server")


@pytest_asyncio.fixture(scope="session")
async def env() -> AsyncIterator[WorkflowEnvironment]:
    os.makedirs(TEST_SERVER_DIR, exist_ok=True)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter,
        download_dest_dir=TEST_SERVER_DIR,
    ) as environment:
        yield environment
