# syntax=docker/dockerfile:1

# --- app: runtime image for both the API and the worker ---------------------------------
FROM python:3.12.16-slim-bookworm AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install . \
    && useradd --create-home --uid 10001 appuser \
    && mkdir /srv/helpdesk \
    && chown appuser /srv/helpdesk

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

# --- tests: app + dev dependencies + the cached Temporal test server ----------------------
FROM app AS tests

USER root
RUN pip install ".[dev]"
COPY tests ./tests
COPY scripts ./scripts
COPY samples ./samples
COPY .env.example docker-compose.yml ./

# Download the time-skipping test server at build time so `pytest` runs with no network.
ENV TEMPORAL_TEST_SERVER_DIR=/srv/.temporal-test-server
RUN python scripts/warm_test_server.py \
    && chown -R appuser /srv

USER appuser
CMD ["pytest", "-p", "no:cacheprovider"]
