import base64
from datetime import date, datetime
from unittest.mock import patch

import pytest
import responses

from jira_client import JiraClient, JiraClientError, JiraTransientError

BASE_URL = "https://jira.example.com"
SEARCH_URL = f"{BASE_URL}/rest/api/3/search/jql"
EMAIL = "user@example.com"
TOKEN = "api-token-123"
FIXED_TODAY = date(2026, 4, 28)

ISSUE = {
    "key": "RC1-42",
    "fields": {
        "summary": "Fix the broken thing",
        "status": {"name": "In Progress"},
        "assignee": {"displayName": "Jane Doe"},
        "updated": "2026-04-14T10:00:00.000+0000",
    },
}


@responses.activate
@patch("jira_client.datetime")
def test_happy_path(mock_dt):
    mock_dt.now.return_value.date.return_value = FIXED_TODAY
    mock_dt.fromisoformat = datetime.fromisoformat
    responses.add(responses.GET, SEARCH_URL, json={"issues": [ISSUE]}, status=200)

    tickets = JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")

    assert len(tickets) == 1
    t = tickets[0]
    assert t["key"] == "RC1-42"
    assert t["summary"] == "Fix the broken thing"
    assert t["status"] == "In Progress"
    assert t["assignee"] == "Jane Doe"
    assert t["url"] == f"{BASE_URL}/browse/RC1-42"
    assert t["days_stale"] == 14


@responses.activate
@patch("jira_client.datetime")
def test_null_assignee_returns_none(mock_dt):
    mock_dt.now.return_value.date.return_value = FIXED_TODAY
    mock_dt.fromisoformat = datetime.fromisoformat
    issue = {
        "key": "RC1-1",
        "fields": {
            "summary": "Task",
            "status": {"name": "To Do"},
            "assignee": None,
            "updated": "2026-04-20T10:00:00.000+0000",
        },
    }
    responses.add(responses.GET, SEARCH_URL, json={"issues": [issue]}, status=200)

    tickets = JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")

    assert tickets[0]["assignee"] is None


@responses.activate
def test_empty_issues_returns_empty_list():
    responses.add(responses.GET, SEARCH_URL, json={"issues": []}, status=200)

    assert JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1") == []


@responses.activate
def test_non_json_response_raises_jira_client_error():
    responses.add(responses.GET, SEARCH_URL, body="<html>Bad Gateway</html>", status=200,
                  content_type="text/html")

    with pytest.raises(JiraClientError, match="non-JSON"):
        JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")


@responses.activate
def test_permanent_error_raises_jira_client_error_immediately():
    responses.add(responses.GET, SEARCH_URL, body="Unauthorized", status=401)

    with pytest.raises(JiraClientError, match="401"):
        JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")

    assert len(responses.calls) == 1


@responses.activate
@patch("time.sleep")
def test_transient_error_retries_then_raises(mock_sleep):
    for _ in range(4):  # stop_after_attempt(4)
        responses.add(responses.GET, SEARCH_URL, body="Service Unavailable", status=503)

    with pytest.raises(JiraTransientError, match="503"):
        JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")

    assert len(responses.calls) == 4


@responses.activate
@patch("time.sleep")
@patch("jira_client.datetime")
def test_transient_error_retries_then_succeeds(mock_dt, mock_sleep):
    mock_dt.now.return_value.date.return_value = FIXED_TODAY
    mock_dt.fromisoformat = datetime.fromisoformat
    responses.add(responses.GET, SEARCH_URL, body="Service Unavailable", status=503)
    responses.add(responses.GET, SEARCH_URL, json={"issues": [ISSUE]}, status=200)

    tickets = JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")

    assert len(tickets) == 1
    assert len(responses.calls) == 2


@responses.activate
def test_jql_with_different_stale_days_encoded_in_url():
    responses.add(responses.GET, SEARCH_URL, json={"issues": []}, status=200)

    client = JiraClient(BASE_URL, EMAIL, TOKEN)
    client.get_stale_tickets('project = RC1 AND updated <= "-7d"')
    client.get_stale_tickets('project = RC1 AND updated <= "-14d"')

    assert "7d" in responses.calls[0].request.url
    assert "14d" in responses.calls[1].request.url


@responses.activate
@patch("jira_client.datetime")
def test_paginates_when_total_exceeds_page_size(mock_dt):
    mock_dt.now.return_value.date.return_value = FIXED_TODAY
    mock_dt.fromisoformat = datetime.fromisoformat
    issue_2 = {**ISSUE, "key": "RC1-43"}
    responses.add(responses.GET, SEARCH_URL, json={"total": 2, "issues": [ISSUE]}, status=200)
    responses.add(responses.GET, SEARCH_URL, json={"total": 2, "issues": [issue_2]}, status=200)

    tickets = JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1", max_results=1)

    assert len(tickets) == 2
    assert tickets[0]["key"] == "RC1-42"
    assert tickets[1]["key"] == "RC1-43"
    assert len(responses.calls) == 2
    assert "startAt=0" in responses.calls[0].request.url
    assert "startAt=1" in responses.calls[1].request.url


@responses.activate
def test_authorization_header_is_base64_encoded():
    responses.add(responses.GET, SEARCH_URL, json={"issues": []}, status=200)

    JiraClient(BASE_URL, EMAIL, TOKEN).get_stale_tickets("project = RC1")

    headers = responses.calls[0].request.headers
    expected = "Basic " + base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    assert headers["Authorization"] == expected
