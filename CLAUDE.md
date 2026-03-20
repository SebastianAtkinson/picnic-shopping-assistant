# Picnic Shopping Assistant

## Project Overview

A Telegram bot that suggests vegetarian recipes based on ingredients the user has available. It uses Claude AI with web search to find recipes specifically from two Dutch cooking websites:
- [miljuschka.nl](https://miljuschka.nl/)
- [uitpaulineskeuken.nl](https://uitpaulineskeuken.nl)

For each suggestion the bot returns: recipe name, a one-sentence description, estimated cooking time, and a verified URL.

Deployed as a containerised application on Google Cloud Run. In production it runs as a webhook; in development it uses long-polling.

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | Telegram bot — handlers, Claude API call, polling/webhook setup |
| `config.py` | Reads all configuration from environment variables |
| `dockerfile` | Multi-stage build (uv for deps, python:3.11-slim runtime) |
| `terraform/main.tf` | Cloud Run service, Artifact Registry, Secret Manager, service account |
| `terraform/variables.tf` | Input variables (project ID, region, tokens) |
| `terraform/outputs.tf` | Outputs: service URL, registry URL, service account |

## Dev Environment Setup

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An Anthropic API key

### Install dependencies

```bash
uv sync
```

### Environment variables

```bash
export TELEGRAM_BOT_TOKEN="your_telegram_token"
export ANTHROPIC_API_KEY="your_anthropic_key"
export ENVIRONMENT="development"   # omit or set to 'development' for polling mode
```

### Run locally

```bash
uv run main.py
```

The bot starts in polling mode and responds to messages immediately.

### Test Anthropic connection

```bash
bash test_anthropic_connection.sh
```

## Docker

```bash
# Build
docker build -t picnic-bot:latest .

# Run
docker run \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e ANTHROPIC_API_KEY="your_key" \
  -e ENVIRONMENT="development" \
  picnic-bot:latest
```

## Deployment (GCP Cloud Run)

```bash
cd terraform

terraform init

terraform apply \
  -var="project_id=your-gcp-project" \
  -var="telegram_bot_token=your_token" \
  -var="anthropic_api_key=your_key" \
  -var="region=europe-west4"
```

In production mode (`ENVIRONMENT=production`), set `WEBHOOK_URL` to the public Cloud Run HTTPS URL. The bot listens on port 8080.

Secrets (`TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`) are stored in GCP Secret Manager and injected at runtime.
