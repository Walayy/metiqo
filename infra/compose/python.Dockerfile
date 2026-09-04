FROM ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 AS uv

FROM python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/

RUN groupadd --gid 10001 metiquo \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin metiquo

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY python ./python
RUN uv sync --frozen --no-dev --no-editable

COPY infra/compose/bootstrap/api_health.py /opt/metiquo-bootstrap/api_health.py
COPY infra/compose/bootstrap/mock_mode_check.py /opt/metiquo-bootstrap/mock_mode_check.py
COPY infra/compose/bootstrap/worker.py /opt/metiquo-bootstrap/worker.py

USER 10001:10001

EXPOSE 8000

CMD ["python", "/opt/metiquo-bootstrap/api_health.py"]
