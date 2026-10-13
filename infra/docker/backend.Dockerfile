FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.12.14-slim-bookworm
COPY --from=uv /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY apps/worker apps/worker
COPY data data
COPY scripts scripts
COPY tests tests
COPY alembic.ini ./
RUN uv sync --frozen
RUN useradd --uid 10001 --create-home actiondesk && chown -R actiondesk:actiondesk /workspace
USER actiondesk
