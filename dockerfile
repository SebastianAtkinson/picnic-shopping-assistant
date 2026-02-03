# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

# Stage 2: Runtime
# This two-stage setup reduces the final image size by only copying the .venv files needed to run the application.
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY src/ .

# Use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "main.py"]