# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml

# Stage 2: Runtime
# This two-stage setup reduces the final image size by only copying the site-packages needed to run the application.
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

COPY main.py picnic_client.py config.py ./

CMD ["python", "main.py"]
