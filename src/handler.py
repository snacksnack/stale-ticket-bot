import json
import logging
import os

import boto3

from jira_client import JiraClient, JiraClientError
from message_builder import build_stale_ticket_message
from slack_client import SlackClient, SlackClientError

_LOG_RECORD_BUILTINS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _LOG_RECORD_BUILTINS}
        entry.update(extras)
        return json.dumps(entry, default=str)


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_root.handlers = [_handler]

logger = logging.getLogger(__name__)

_STALE_DAYS = int(os.environ["STALE_DAYS"])
_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]
_JQL = (
    f'project = {_PROJECT_KEY} '
    f'AND status in ("To Do", "In Progress", "In Review") '
    f'AND issueType != Epic '
    f'AND updated <= "-{_STALE_DAYS}d" '
    f'ORDER BY updated ASC'
)
# The Slack bot token belongs to the incident summarizer's app (secret
# `incident-summarizer-slackbot`); this stack is granted read access to it in
# template.yaml. One Slack app for the estate, one credential to rotate.
_SLACK_TOKEN_SECRET = os.environ["SLACK_BOT_TOKEN_SECRET_NAME"]
_SLACK_CHANNEL_ID = os.environ["SLACK_CHANNEL_ID"]
_secrets = boto3.client("secretsmanager")
_cloudwatch = boto3.client("cloudwatch")


def lambda_handler(event, context):
    logger.info("stale-ticket-bot started", extra={"jql_used": _JQL})
    try:
        jira_raw = _secrets.get_secret_value(SecretId="stale-bot/jira-api-token")["SecretString"]
        jira_secret = json.loads(jira_raw)
        slack_token = _secrets.get_secret_value(SecretId=_SLACK_TOKEN_SECRET)["SecretString"]

        with JiraClient(
            base_url=os.environ["JIRA_BASE_URL"],
            email=jira_secret["email"],
            api_token=jira_secret["api_token"],
        ) as jira:
            tickets = jira.get_stale_tickets(_JQL)

        try:
            _cloudwatch.put_metric_data(
                Namespace="StaleTicketBot",
                MetricData=[{
                    "MetricName": "StaleTicketCount",
                    "Value": len(tickets),
                    "Unit": "Count",
                }],
            )
        except Exception as exc:
            logger.warning("metric emit failed", extra={"error": str(exc)})

        if not tickets:
            logger.info("no stale tickets found, skipping Slack post")
            return

        payload = build_stale_ticket_message(tickets, _STALE_DAYS)
        SlackClient(slack_token, _SLACK_CHANNEL_ID).post_message(payload)

        logger.info("stale-ticket-bot completed", extra={"ticket_count": len(tickets)})
    except JiraClientError as exc:
        logger.error("jira fetch failed", extra={"error": str(exc), "error_type": type(exc).__name__})
        raise
    except SlackClientError as exc:
        logger.error("slack post failed", extra={"error": str(exc), "error_type": type(exc).__name__})
        raise
    except Exception as exc:
        logger.error("unexpected error", extra={"error": str(exc), "error_type": type(exc).__name__})
        raise
