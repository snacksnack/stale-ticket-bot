# stale-ticket-bot

AWS Lambda function that runs on a weekday morning schedule (9 AM ET), queries Jira for stale tickets, and posts a Slack Block Kit reminder. Deployed with AWS SAM.

## Prerequisites

- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
- Python 3.12
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- Two secrets in AWS Secrets Manager (see below)

## Secrets Manager Setup

These secrets must be created manually before deploying. **Never commit secret values to the repository.**

### `stale-bot/jira-api-token`

Stores Jira credentials as a JSON key/value pair.

**Structure:**
```json
{
  "email": "your-jira-account@example.com",
  "api_token": "your-jira-api-token"
}
```

**Create via AWS CLI:**
```bash
aws secretsmanager create-secret \
  --name stale-bot/jira-api-token \
  --secret-string '{"email":"your-jira-account@example.com","api_token":"your-jira-api-token"}'
```

Generate a Jira API token at: https://id.atlassian.com/manage-profile/security/api-tokens

---

### `stale-bot/slack-webhook-url`

Stores the Slack Incoming Webhook URL as a plain string.

**Structure:**
```
https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
```

**Create via AWS CLI:**
```bash
aws secretsmanager create-secret \
  --name stale-bot/slack-webhook-url \
  --secret-string 'https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX'
```

Create a Slack Incoming Webhook at: https://api.slack.com/messaging/webhooks

---

## CI/CD

Deployments run via GitHub Actions using OIDC — no long-lived AWS keys are stored in GitHub secrets.

| Resource | Value |
|----------|-------|
| OIDC provider | `token.actions.githubusercontent.com` |
| Deploy role ARN | `arn:aws:iam::727323477998:role/stale-ticket-bot-deploy-role` |

The trust policy is scoped to the `snacksnack/stale-ticket-bot` repository. The role grants only what SAM needs: CloudFormation, Lambda, S3, IAM role creation, SQS, and EventBridge.

## Deployment

Both secrets must exist before the first deploy.

```bash
# Build
sam build

# First deploy (prompts for AlertEmail parameter)
sam deploy --guided

# Subsequent deploys
sam deploy
```

`samconfig.toml` captures all deploy defaults (stack name, region, S3 artifact bucket) after the first guided deploy.

## Local Development

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run unit tests
python -m pytest tests/unit -v

# Run unit tests with coverage report
python -m pytest tests/unit -v --cov=src --cov-report=term-missing

# Validate the SAM template
sam validate

# Local invoke with the sample EventBridge event
sam local invoke StaleTicketBotFunction --event events/event.json
```

## Testing

Unit tests live in `tests/unit/` and an integration test in `tests/integration/`. Coverage is 100% across all of `src/`.

```bash
# Run unit tests only
python -m pytest tests/unit -v

# Run all tests (unit + integration)
python -m pytest tests/unit tests/integration -v --cov=src --cov-report=term-missing
```

**HTTP client:** `jira_client.py` uses `requests.Session` (Basic auth via `session.auth`, JSON via `response.json()`). `slack_client.py` uses `requests.post(..., json=payload)`. Both use `requests` consistently so the `responses` library can intercept their calls in tests.

**Unit test mocking:**

`jira_client.py` and `slack_client.py` are tested with `@responses.activate` + `responses.add()` — no manual urllib3 patching needed.

`handler.py` exposes a module-level `_secrets` boto3 client (intentional — reused across warm invocations). Unit tests patch `handler._secrets` directly, keeping them fast without a full moto environment.

`tests/conftest.py` inserts `src/` into `sys.path` so all test files can import the Lambda source modules without packaging.

**Integration test (`tests/integration/test_handler_integration.py`):**

Exercises the full handler wiring end-to-end without hitting any real external APIs:

- `@mock_aws` (moto) seeds Secrets Manager with test credentials
- `responses.RequestsMock()` mocks the Jira search endpoint and Slack webhook
- `handler._secrets` is patched with a boto3 client created inside the moto context
- Assertions verify the exact Slack Block Kit payload — header text, ticket key, summary, and assignee

A local `responses.RequestsMock()` context manager is used rather than the `@responses.activate` decorator because moto 5 touches the global `responses` state, which causes `responses.calls` to appear empty even when calls succeed. Using a local instance and reading from `rsps.calls` avoids this.

**What is covered:**

| Module | Scenarios |
|--------|-----------|
| `jira_client.py` | Happy path, null assignee, empty issue list, non-200 response, JQL encoding for different stale-day values, Basic auth header |
| `slack_client.py` | Happy path, non-200 response, 200 with non-`ok` body, JSON body + Content-Type header |
| `message_builder.py` | Empty list → `None`, singular/plural noun, block structure, ticket field rendering, inter-ticket dividers, null assignee → "Unassigned", stale days in footer |
| `handler.py` (unit) | Happy path, no tickets skips Slack, Jira error re-raised, Slack error re-raised, JQL contains configured stale days |
| `handler.py` (integration) | Full end-to-end wiring: Secrets Manager → Jira fetch → message build → Slack POST |

## Staleness Definition

A ticket is considered stale when it has had no activity (comments, field edits, status transitions) for `STALE_DAYS` days (default: 7) and is still open.

**JQL query:**
```
project = RC1
AND status in ("To Do", "In Progress", "In Review")
AND issueType != Epic
AND updated <= "-7d"
ORDER BY updated ASC
```

- `status in (...)` — targets only active workflow states; excludes `Idea` (ungroomed backlog) and `Done`
- `issueType != Epic` — excludes Epics, which are intentionally long-lived
- `updated <= "-7d"` — `updated` covers all activity types; driven by the `STALE_DAYS` CloudFormation parameter at runtime
- `ORDER BY updated ASC` — most neglected tickets surface first

## Lambda Handler

- `boto3.client("secretsmanager")` and `boto3.client("cloudwatch")` are initialised at module level so they are reused across warm Lambda invocations rather than re-created on every call
- `JIRA_BASE_URL` is read via `os.environ["JIRA_BASE_URL"]` (not `.get()`) so the function fails loudly at startup if the variable is missing, rather than producing a confusing error later
- `JIRA_BASE_URL` is a CloudFormation parameter (not a secret) — supply your Jira instance URL (e.g. `https://your-org.atlassian.net`) at deploy time
- After every successful Jira fetch the handler emits a `StaleTicketCount` custom metric — including when the count is 0 — so gaps in the metric are meaningful rather than ambiguous
- If no stale tickets are found the handler logs and returns early without posting to Slack

## Custom Metrics

The handler emits one custom CloudWatch metric per invocation:

| Namespace | Metric | Unit | Notes |
|-----------|--------|------|-------|
| `StaleTicketBot` | `StaleTicketCount` | Count | Number of stale tickets found; emitted even when 0 so the metric is always present |

The metric is only emitted after a successful Jira API call. If the call fails (and the event lands in the DLQ), no metric is emitted for that invocation, which itself acts as a signal.

You can graph `StaleTicketCount` over time in CloudWatch and set an alarm if it rises above a threshold that would indicate an unusual backlog.

## Block Kit Message Structure

- Returns `None` when `tickets` is empty so the handler can skip the Slack POST entirely rather than sending an empty message
- Dividers appear between tickets, not after the last one
- The header uses singular/plural ("1 ticket" vs "2 tickets")
- Unassigned tickets show `Unassigned` rather than a blank field
- Each ticket's summary appears on its own line for readability

## Jira Client Retry Behaviour

Transient Jira API errors (HTTP 429, 500, 502, 503, 504) are retried automatically using `tenacity`. Permanent errors (401, 403, 410, etc.) are not retried.

| Setting | Value |
|---------|-------|
| Total attempts | 4 (1 original + 3 retries) |
| Backoff | Exponential — 1s, 2s, 4s (capped at 8s) |
| Retry on | `JiraTransientError` (subclass of `JiraClientError`) |
| After exhaustion | Re-raises `JiraTransientError`; handler logs and re-raises, landing the event in the DLQ |

`JiraTransientError` is a subclass of `JiraClientError` so callers that catch `JiraClientError` continue to work without changes.

## Slack Webhook Behaviour

- The response body is checked in addition to the HTTP status — Slack can return `200` with an error string (e.g. `invalid_payload`) if the JSON is malformed, so a `200` alone is not sufficient to confirm success
- The HTTP status and response body are always logged before any exception is raised, so failures are observable in CloudWatch even when the exception is caught upstream
- `post_message` returns `None`; callers only need to handle the happy path or catch `SlackClientError`

## Alarms

All three alarms send email via the `DLQAlarmTopic` SNS topic (address set by the `AlertEmail` CloudFormation parameter).

| Alarm | Metric | Condition | Notes |
|-------|--------|-----------|-------|
| `stale-ticket-bot-dlq-depth` | SQS `ApproximateNumberOfMessagesVisible` | > 0 | Lambda failed and a message landed in the DLQ |
| `stale-ticket-bot-lambda-errors` | Lambda `Errors` | > 0 over 5 min | Lambda threw an unhandled error; `TreatMissingData: notBreaching` so quiet periods don't false-alarm |
| `stale-ticket-bot-missing-invocation` | Lambda `Invocations` | < 1 over 24 hours | EventBridge schedule may have stopped; `TreatMissingData: breaching` so a missing data point is treated as a failure |

**Weekend false positives:** The missing-invocation alarm will fire on weekends because the Lambda correctly does not run then — Lambda emits no data point when it isn't invoked, so CloudWatch cannot distinguish "didn't run on a weekday" from "it's Saturday." This is a known CloudWatch limitation with no native workaround for schedules that don't run every day.

## Architecture

```
EventBridge (cron, 9 AM ET weekdays)
    └── Lambda (StaleTicketBotFunction)
            ├── Secrets Manager (jira-api-token, slack-webhook-url)
            ├── Jira REST API  →  fetch stale tickets
            ├── Slack Webhook  →  post Block Kit message
            └── SQS DLQ        →  on failure
                    └── CloudWatch Alarms (DLQ depth, Lambda errors, missing invocation)
                            └── SNS → email
```

**Source layout:**

| File | Responsibility |
|------|---------------|
| `src/handler.py` | Lambda entry point; fetches secrets, orchestrates modules |
| `src/jira_client.py` | `get_stale_tickets(jql, max_results)` |
| `src/message_builder.py` | `build_stale_ticket_message(tickets, stale_days)` |
| `src/slack_client.py` | `post_message(payload)` |

**Configuration:** `STALE_DAYS` is a CloudFormation parameter (default: 7), passed to the Lambda as an environment variable.

## Cleanup

```bash
sam delete --stack-name stale-ticket-bot
```
