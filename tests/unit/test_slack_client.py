import json

import pytest
import responses
from unittest.mock import patch

from slack_client import SlackClient, SlackClientError, SlackTransientError

WEBHOOK_URL = "https://hooks.slack.com/services/T00/B00/test"
PAYLOAD = {"blocks": [{"type": "header", "text": {"type": "plain_text", "text": "Test"}}]}


@responses.activate
def test_happy_path_posts_successfully():
    responses.add(responses.POST, WEBHOOK_URL, body="ok", status=200)

    SlackClient(WEBHOOK_URL).post_message(PAYLOAD)

    assert len(responses.calls) == 1


@responses.activate
@patch("time.sleep")
def test_transient_error_retries_then_raises(mock_sleep):
    for _ in range(4):
        responses.add(responses.POST, WEBHOOK_URL, body="Service Unavailable", status=503)

    with pytest.raises(SlackTransientError, match="503"):
        SlackClient(WEBHOOK_URL).post_message(PAYLOAD)

    assert len(responses.calls) == 4


@responses.activate
@patch("time.sleep")
def test_transient_error_retries_then_succeeds(mock_sleep):
    responses.add(responses.POST, WEBHOOK_URL, body="Service Unavailable", status=503)
    responses.add(responses.POST, WEBHOOK_URL, body="ok", status=200)

    SlackClient(WEBHOOK_URL).post_message(PAYLOAD)

    assert len(responses.calls) == 2


@responses.activate
def test_permanent_error_raises_immediately():
    responses.add(responses.POST, WEBHOOK_URL, body="invalid_token", status=403)

    with pytest.raises(SlackClientError, match="403"):
        SlackClient(WEBHOOK_URL).post_message(PAYLOAD)

    assert len(responses.calls) == 1


@responses.activate
def test_200_with_non_ok_body_raises_slack_client_error():
    responses.add(responses.POST, WEBHOOK_URL, body="invalid_payload", status=200)

    with pytest.raises(SlackClientError, match="invalid_payload"):
        SlackClient(WEBHOOK_URL).post_message(PAYLOAD)


@responses.activate
def test_payload_sent_as_json_with_content_type():
    responses.add(responses.POST, WEBHOOK_URL, body="ok", status=200)

    SlackClient(WEBHOOK_URL).post_message(PAYLOAD)

    req = responses.calls[0].request
    assert json.loads(req.body) == PAYLOAD
    assert "application/json" in req.headers["Content-Type"]
