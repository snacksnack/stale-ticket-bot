import base64
import json
import logging
import urllib.parse
import urllib3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class JiraClientError(Exception):
    pass


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        credentials = base64.b64encode(
            f"{email}:{api_token}".encode()
        ).decode()
        self._headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }
        self._http = urllib3.PoolManager()

    def get_stale_tickets(self, jql: str, max_results: int = 50) -> list[dict]:
        params = urllib.parse.urlencode({
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,updated",
        })
        url = f"{self.base_url}/rest/api/3/search?{params}"
        logger.info("fetching stale tickets", extra={"jql_used": jql})
        response = self._http.request("GET", url, headers=self._headers)
        if response.status != 200:
            raise JiraClientError(
                f"Jira API returned {response.status}: "
                f"{response.data.decode()}"
            )
        data = json.loads(response.data)
        today = datetime.now(timezone.utc).date()
        tickets = []
        for issue in data.get("issues", []):
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
