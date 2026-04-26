# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python 3.12 AWS Lambda function deployed with AWS SAM. It runs on a weekday morning EventBridge schedule (9AM ET), fetches stale Jira tickets, and posts a Slack Block Kit reminder. Failed executions route to an SQS dead-letter queue, which triggers a CloudWatch alarm via SNS email.

## Commands

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run unit tests
python -m pytest tests/unit -v

# Run a single test file
python -m pytest tests/unit/test_jira_client.py -v

# Lint
flake8 src/

# Build (cached + parallel, configured in samconfig.toml)
sam build

# Local invoke with the sample EventBridge event
sam local invoke StaleTicketBotFunction --event events/event.json

# Validate SAM template (linting enabled by default)
sam validate

# Deploy (first time; subsequent deploys: sam deploy)
sam deploy --guided

# Integration tests (requires a deployed stack)
AWS_SAM_STACK_NAME="stale-ticket-bot" python -m pytest tests/integration -v
```

## Architecture

**Execution flow** (all in `src/`):

1. `handler.py` — Lambda entry point; fetches secrets from Secrets Manager, orchestrates the three modules below, logs structured JSON at start/end.
2. `jira_client.py` — `get_stale_tickets(jql, max_results)` — queries Jira REST API for tickets inactive longer than `STALE_DAYS`.
3. `message_builder.py` — `build_stale_ticket_message(tickets, stale_days)` — produces a Slack Block Kit payload.
4. `slack_client.py` — `post_message(payload)` — POSTs to the Slack incoming webhook URL.

**Configuration:**
- `STALE_DAYS` env var is set via the `StaleDays` CloudFormation parameter (default: 7).
- Secrets are in AWS Secrets Manager: `stale-bot/jira-api-token` and `stale-bot/slack-webhook-url`.

**Infrastructure (`template.yaml`):** Lambda + EventBridge schedule + SQS DLQ + CloudWatch alarm + SNS email topic. `samconfig.toml` captures all deploy defaults so `sam build` and `sam deploy` need no extra flags after first deployment.

**Testing:** Unit tests use `moto[secretsmanager]` for Secrets Manager mocking and `responses` for HTTP mocking (Jira/Slack). Integration tests require a live deployed stack.
