FROM ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 AS uv

FROM python:3.13.14-slim-trixie@sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6

ENV PATH="/app/.venv/bin:/usr/lib/postgresql/18/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/

RUN apt-get update \
    && apt-get upgrade --no-install-recommends -y \
    && apt-get install --no-install-recommends -y ca-certificates age \
    && mkdir -p /usr/share/postgresql-common/pgdg \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://www.postgresql.org/media/keys/ACCC4CF8.asc', '/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc')" \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 metiquo \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin metiquo

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY alembic.ini ./
COPY config ./config
COPY python ./python
RUN uv sync --frozen --no-dev --no-editable && rm -f /bin/uv /bin/uvx

# Immutable runtime: invoke the native PostgreSQL tools directly. Debian's
# pg_wrapper and maintenance scripts need Perl; the application never uses them.
# Keep PostgreSQL/libpq package records so image audits still inventory them.
# Rebuild the image for upgrades; do not run apt/dpkg in this reduced runtime.
RUN dpkg --purge --force-depends --force-remove-essential \
        perl perl-base libperl5.40 perl-modules-5.40 \
    && pg_dump --version && pg_restore --version

COPY infra/compose/bootstrap/mock_mode_check.py /opt/metiquo-bootstrap/mock_mode_check.py

USER 10001:10001

ARG APP_CODE_COMMIT=""
ENV APP_CODE_COMMIT=$APP_CODE_COMMIT
LABEL org.opencontainers.image.revision=$APP_CODE_COMMIT

EXPOSE 8000

CMD ["python", "/opt/metiquo-bootstrap/api_health.py"]
