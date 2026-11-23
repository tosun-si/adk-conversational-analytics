FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV APP_DIR=/usr/local/src/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR ${APP_DIR}

# Deps first: this layer survives code/prompt changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# slim, not alpine: vl-convert and grpcio ship glibc wheels.
FROM python:3.12-slim

ENV APP_DIR=/usr/local/src/app
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --create-home appuser

WORKDIR ${APP_DIR}

COPY --from=builder --chown=appuser:appuser ${APP_DIR}/.venv ${APP_DIR}/.venv
COPY --chown=appuser:appuser agents/ ./agents/

ENV PATH="${APP_DIR}/.venv/bin:$PATH"

USER appuser

EXPOSE 8080

ENTRYPOINT ["adk"]
CMD ["web", "--host", "0.0.0.0", "--port", "8080", "agents"]
