import json
import os
from unittest.mock import patch

import boto3
import responses
from moto import mock_aws

import handler

JIRA_BASE_URL = "https://jira.example.com"
JIRA_SEARCH_URL = f"{JIRA_BASE_URL}/rest/api/3/search"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T00/B00/test"
JIRA_SECRET = {"email": "user@example.com", "api_token": "tok"}

JIRA_RESPONSE = {
    "issues": [
        {
            "key": "RC1-42",
            "fields": {
                "summary": "Fix the broken thing",
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "Jane Doe"},
                "updated": "2026-04-01T10:00:00.000+0000",
            },
        }
    ]
}

# Fake credentials satisfy boto3/moto; no real AWS calls are made.
_AWS_ENV = {
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
}


@mock_aws
@patch.dict(os.environ, {"JIRA_BASE_URL": JIRA_BASE_URL, **_AWS_ENV})
def test_handler_end_to_end_posts_to_slack():
    # Seed Secrets Manager with test credentials.
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    sm.create_secret(
        Name="stale-bot/jira-api-token",
        SecretString=json.dumps(JIRA_SECRET),
    )
    sm.create_secret(
        Name="stale-bot/slack-webhook-url",
        SecretString=SLACK_WEBHOOK_URL,
    )

    # Mock the Jira and Slack HTTP calls via a local RequestsMock so that
    # rsps.calls is isolated from any global state that @mock_aws may touch.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(rsps.GET, JIRA_SEARCH_URL, json=JIRA_RESPONSE, status=200)
        rsps.add(rsps.POST, SLACK_WEBHOOK_URL, body="ok", status=200)

        # Replace the module-level boto3 client with one created inside the mock
        # context so Secrets Manager lookups resolve against the seeded secrets.
        with patch("handler._secrets", sm):
            handler.lambda_handler({}, {})

        # Verify the Slack POST was made and contains the expected ticket data.
        slack_calls = [c for c in rsps.calls if SLACK_WEBHOOK_URL in c.request.url]
        assert len(slack_calls) == 1

        payload = json.loads(slack_calls[0].request.body)

    assert "blocks" in payload

    header_text = payload["blocks"][0]["text"]["text"]
    assert "Stale Ticket Reminder: 1 ticket" == header_text

    message = json.dumps(payload)
    assert "RC1-42" in message
    assert "Fix the broken thing" in message
    assert "Jane Doe" in message
