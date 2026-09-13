import json
import os
from unittest.mock import patch

import pytest

import handler
from jira_client import JiraClientError
from slack_client import SlackClientError

JIRA_SECRET = {"email": "user@example.com", "api_token": "tok"}
SLACK_TOKEN = "xoxb-test"
TICKET = {
    "key": "RC1-1",
    "summary": "Fix thing",
    "status": "In Progress",
    "assignee": "Jane Doe",
    "url": "https://jira.example.com/browse/RC1-1",
    "days_stale": 10,
}

ENV = {
    "JIRA_BASE_URL": "https://jira.example.com",
    "JIRA_PROJECT_KEY": "RC1",
    "STALE_DAYS": "7",
    "SLACK_BOT_TOKEN_SECRET_NAME": "incident-summarizer-slackbot",
    "SLACK_CHANNEL_ID": "C0TEST",
}


def _secrets_side_effect(*_args, SecretId=None, **_kwargs):
    if "jira" in SecretId:
        return {"SecretString": json.dumps(JIRA_SECRET)}
    return {"SecretString": SLACK_TOKEN}


def _setup_jira_mock(mock_jira_cls):
    # handler.py uses `with JiraClient(...) as jira:`, so __enter__ must return
    # the same mock instance that get_stale_tickets is configured on.
    mock_jira_cls.return_value.__enter__.return_value = mock_jira_cls.return_value


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_happy_path_posts_to_slack(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = [TICKET]

    handler.lambda_handler({}, {})

    mock_slack_cls.assert_called_once_with(SLACK_TOKEN, "C0TEST")
    mock_slack_cls.return_value.post_message.assert_called_once()


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_no_tickets_skips_slack(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = []

    handler.lambda_handler({}, {})

    mock_slack_cls.return_value.post_message.assert_not_called()


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_jira_error_is_reraised(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.side_effect = JiraClientError("boom")

    with pytest.raises(JiraClientError):
        handler.lambda_handler({}, {})


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_slack_error_is_reraised(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = [TICKET]
    mock_slack_cls.return_value.post_message.side_effect = SlackClientError("boom")

    with pytest.raises(SlackClientError):
        handler.lambda_handler({}, {})


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_jql_contains_stale_days_and_project(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = []

    handler.lambda_handler({}, {})

    jql_used = mock_jira_cls.return_value.get_stale_tickets.call_args[0][0]
    stale_days = handler._STALE_DAYS
    assert f"-{stale_days}d" in jql_used
    assert "RC1" in jql_used


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_emits_ticket_count_metric(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = [TICKET]

    handler.lambda_handler({}, {})

    mock_cw.put_metric_data.assert_called_once_with(
        Namespace="StaleTicketBot",
        MetricData=[{
            "MetricName": "StaleTicketCount",
            "Value": 1,
            "Unit": "Count",
        }],
    )


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_emits_zero_count_when_no_tickets(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = []

    handler.lambda_handler({}, {})

    mock_cw.put_metric_data.assert_called_once_with(
        Namespace="StaleTicketBot",
        MetricData=[{
            "MetricName": "StaleTicketCount",
            "Value": 0,
            "Unit": "Count",
        }],
    )


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_unexpected_error_is_reraised(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = RuntimeError("something weird")

    with pytest.raises(RuntimeError):
        handler.lambda_handler({}, {})


@patch.dict(os.environ, ENV)
@patch("handler._cloudwatch")
@patch("handler._secrets")
@patch("handler.SlackClient")
@patch("handler.JiraClient")
def test_metric_failure_does_not_fail_lambda(mock_jira_cls, mock_slack_cls, mock_secrets, mock_cw):
    _setup_jira_mock(mock_jira_cls)
    mock_secrets.get_secret_value.side_effect = _secrets_side_effect
    mock_jira_cls.return_value.get_stale_tickets.return_value = [TICKET]
    mock_cw.put_metric_data.side_effect = Exception("throttled")

    handler.lambda_handler({}, {})

    mock_slack_cls.return_value.post_message.assert_called_once()
