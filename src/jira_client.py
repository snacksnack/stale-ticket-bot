import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class JiraClientError(Exception):
    pass


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = (email, api_token)
        self._session.headers["Accept"] = "application/json"

    def get_stale_tickets(self, jql: str, max_results: int = 50) -> list[dict]:
        url = f"{self.base_url}/rest/api/3/search/jql"
        logger.info("fetching stale tickets", extra={"jql_used": jql})
        response = self._session.get(url, params={
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,updated",
        })
        if response.status_code != 200:
            raise JiraClientError(
                f"Jira API returned {response.status_code}: {response.text}"
            )
        today = datetime.now(timezone.utc).date()
        tickets = []
        for issue in response.json().get("issues", []):
            fields = issue["fields"]
            updated = datetime.fromisoformat(
                fields["updated"].replace("Z", "+00:00")
            ).date()
            assignee = fields.get("assignee")
            tickets.append({
                "key": issue["key"],
                "summary": fields["summary"],
                "status": fields["status"]["name"],
                "assignee": assignee["displayName"] if assignee else None,
                "url": f"{self.base_url}/browse/{issue['key']}",
                "days_stale": (today - updated).days,
            })
        logger.info(
            "stale tickets fetched",
            extra={"ticket_count": len(tickets)},
        )
        return tickets
