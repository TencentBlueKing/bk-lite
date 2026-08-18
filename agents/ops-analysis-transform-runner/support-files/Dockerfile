FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRANSFORM_ORG_CONCURRENCY=3 \
    TRANSFORM_TIMEOUT_SECONDS=5 \
    PORT=8099

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin runner

COPY pyproject.toml uv.lock /app/
COPY app /app/app

RUN pip install --no-cache-dir uv==0.11.1 \
    && uv sync --frozen --no-dev \
    && chown -R runner:runner /app

ENV PATH="/app/.venv/bin:${PATH}"

USER runner
EXPOSE 8099

# Production: --read-only, no public host ports, internal network with no egress,
# TRANSFORM_RUNNER_TOKEN required, replicas=1, --workers 1 (already set).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--workers", "1"]
