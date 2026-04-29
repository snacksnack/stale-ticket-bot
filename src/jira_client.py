import logging
import requests
from datetime import datetime, timezone
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS_CODES = frozenset([429, 500, 502, 503, 504])


class JiraClientError(Exception):
    pass


class JiraTransientError(JiraClientError):
    pass


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = (email, api_token)
        self._session.headers["Accept"] = "application/json"

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(JiraTransientError),
        reraise=True,
    )
    def get_stale_tickets(self, jql: str, max_results: int = 50) -> list[dict]:
        url = f"{self.base_url}/rest/api/3/search/jql"
        logger.info("fetching stale tickets", extra={"jql_used": jql})
        response = self._session.get(url, params={
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,updated",
        }, timeout=10)
        if response.status_code in _TRANSIENT_STATUS_CODES:
            raise JiraTransientError(f"Jira API returned {response.status_code}: {response.text}")
        if response.status_code != 200:
            raise JiraClientError(f"Jira API returned {response.status_code}: {response.text}")
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise JiraClientError(f"Jira API returned non-JSON response: {response.text[:200]}") from exc
        total = data.get("total", 0)
        if total > max_results:
            logger.warning(
                "jira result truncated — increase max_results or add pagination",
                extra={"total": total, "max_results": max_results},
            )
        today = datetime.now(timezone.utc).date()
        tickets = []
        for issue in data.get("issues", []):
            fields = issue["fields"]
            updated = datetime.fromisoformat(fields["updated"].replace("Z", "+00:00")).date()
            assignee = fields.get("assignee")
            tickets.append({
                "key": issue["key"],
                "summary": fields["summary"],
                "status": fields["status"]["name"],
                "assignee": assignee["displayName"] if assignee else None,
                "url": f"{self.base_url}/browse/{issue['key']}",
                "days_stale": (today - updated).days,
            })
        logger.info("stale tickets fetched", extra={"ticket_count": len(tickets)})
        return tickets
