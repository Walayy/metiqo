FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN pip install --no-cache-dir uv==0.11.23
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

FROM base AS api
RUN uv sync --frozen --no-dev --package metiquo-api --no-install-workspace \
    && groupadd --gid 10001 metiquo && useradd --uid 10001 --gid 10001 --create-home metiquo
COPY packages/core packages/core
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package metiquo-api --no-editable
COPY alembic.ini ./
COPY migrations migrations
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "metiquo_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

FROM base AS test
RUN uv sync --frozen --no-install-workspace
COPY packages/core packages/core
COPY apps/api apps/api
COPY apps/worker apps/worker
COPY alembic.ini ./
COPY migrations migrations
COPY tests/backend tests/backend
COPY docs/audits/matching docs/audits/matching
RUN uv sync --frozen
ENV PATH="/app/.venv/bin:$PATH"
CMD ["pytest", "-m", "integration", "-q"]

FROM base AS worker
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN uv sync --frozen --no-dev --package metiquo-worker --no-install-workspace \
    && uv run --no-sync patchright install --with-deps --no-shell chromium \
    && groupadd --gid 10001 metiquo && useradd --uid 10001 --gid 10001 --create-home metiquo \
    && mkdir -p /data/artifacts /data/browser && chown -R 10001:10001 /data /opt/browsers
COPY packages/core packages/core
COPY apps/worker apps/worker
RUN uv sync --frozen --no-dev --package metiquo-worker --no-editable
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
CMD ["metiquo-worker", "serve"]

FROM worker AS stake
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/* \
    && patchright install chrome
USER 10001:10001
CMD ["xvfb-run", "-a", "metiquo-worker", "serve", "--only", "stake"]
