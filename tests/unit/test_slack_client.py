import json

import pytest
import responses
from unittest.mock import patch

from slack_client import SlackClient, SlackClientError, SlackTransientError

API_URL = "https://slack.com/api/chat.postMessage"
PAYLOAD = {"text": "Test", "blocks": [{"type": "header", "text": {"type": "plain_text", "text": "Test"}}]}


def _client():
    return SlackClient("xoxb-test", "C0TEST")


@responses.activate
def test_happy_path_returns_ts():
    responses.add(responses.POST, API_URL, json={"ok": True, "ts": "1700000000.000100"}, status=200)

    ts = _client().post_message(PAYLOAD)

    assert ts == "1700000000.000100"
    assert len(responses.calls) == 1


@responses.activate
@patch("time.sleep")
def test_transient_http_error_retries_then_raises(mock_sleep):
    for _ in range(4):
        responses.add(responses.POST, API_URL, body="Service Unavailable", status=503)

    with pytest.raises(SlackTransientError, match="503"):
        _client().post_message(PAYLOAD)

    assert len(responses.calls) == 4


@responses.activate
@patch("time.sleep")
def test_transient_http_error_retries_then_succeeds(mock_sleep):
    responses.add(responses.POST, API_URL, body="Service Unavailable", status=503)
    responses.add(responses.POST, API_URL, json={"ok": True, "ts": "1.0"}, status=200)

    _client().post_message(PAYLOAD)

    assert len(responses.calls) == 2


@responses.activate
@patch("time.sleep")
def test_ratelimited_api_error_is_transient(mock_sleep):
    responses.add(responses.POST, API_URL, json={"ok": False, "error": "ratelimited"}, status=200)
    responses.add(responses.POST, API_URL, json={"ok": True, "ts": "1.0"}, status=200)

    _client().post_message(PAYLOAD)

    assert len(responses.calls) == 2


@responses.activate
def test_permanent_http_error_raises_immediately():
    responses.add(responses.POST, API_URL, body="Forbidden", status=403)

    with pytest.raises(SlackClientError, match="403"):
        _client().post_message(PAYLOAD)

    assert len(responses.calls) == 1


@responses.activate
def test_api_error_raises_slack_client_error_with_the_error_code():
    # not_in_channel is what a public channel answers before /invite; it must
    # surface by name, not as a bare non-200.
    responses.add(responses.POST, API_URL, json={"ok": False, "error": "not_in_channel"}, status=200)

    with pytest.raises(SlackClientError, match="not_in_channel"):
        _client().post_message(PAYLOAD)

    assert len(responses.calls) == 1


@responses.activate
def test_non_json_200_body_raises_slack_client_error():
    responses.add(responses.POST, API_URL, body="<html>", status=200)

    with pytest.raises(SlackClientError, match="unknown_error"):
        _client().post_message(PAYLOAD)


@responses.activate
def test_request_carries_channel_bearer_token_and_payload():
    responses.add(responses.POST, API_URL, json={"ok": True, "ts": "1.0"}, status=200)

    _client().post_message(PAYLOAD)

    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer xoxb-test"
    assert req.headers["Content-Type"] == "application/json"
    assert json.loads(req.body) == {"channel": "C0TEST", **PAYLOAD}
