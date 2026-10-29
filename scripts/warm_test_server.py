"""Download the Temporal time-skipping test server once, so later test runs are offline.

Run at image build time by the ``tests`` Docker target, or once on a host before the first
``pytest`` run. The binary is cached in ``$TEMPORAL_TEST_SERVER_DIR``
(default ``.temporal-test-server``), the same directory ``tests/conftest.py`` uses.
"""

import asyncio
import os

from temporalio.testing import WorkflowEnvironment


async def main() -> None:
    directory = os.environ.get("TEMPORAL_TEST_SERVER_DIR", ".temporal-test-server")
    os.makedirs(directory, exist_ok=True)
    async with await WorkflowEnvironment.start_time_skipping(download_dest_dir=directory):
        pass
    print(f"Temporal test server cached in {directory}")


if __name__ == "__main__":
    asyncio.run(main())
