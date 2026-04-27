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

# Validate the SAM template
sam validate

# Local invoke with the sample EventBridge event
sam local invoke StaleTicketBotFunction --event events/event.json
```

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

## Architecture

```
EventBridge (cron, 9 AM ET weekdays)
    └── Lambda (StaleTicketBotFunction)
            ├── Secrets Manager (jira-api-token, slack-webhook-url)
            ├── Jira REST API  →  fetch stale tickets
            ├── Slack Webhook  →  post Block Kit message
            └── SQS DLQ        →  on failure
                    └── CloudWatch Alarm → SNS → email
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
