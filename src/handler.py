import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Stale Ticket Bot — Lambda entry point.
    Triggered by EventBridge on weekday mornings.
    Fetches stale Jira tickets and posts a Slack reminder.
    """
    logger.info(json.dumps({"message": "stale-ticket-bot started", "event": event}))

    # TODO: fetch secrets from Secrets Manager
    # TODO: instantiate JiraClient and fetch stale tickets
    # TODO: build Block Kit message
    # TODO: post to Slack

    logger.info(json.dumps({"message": "stale-ticket-bot completed"}))
