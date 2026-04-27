import json
import logging
import urllib3

logger = logging.getLogger(__name__)


class SlackClientError(Exception):
    pass


class SlackClient:
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url
        self._http = urllib3.PoolManager()

    def post_message(self, payload: dict) -> None:
        response = self._http.request(
            "POST",
            self._webhook_url,
            body=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        body = response.data.decode()
        logger.info(
            "slack webhook response",
            extra={"slack_status": response.status, "slack_response": body},
        )
        if response.status != 200 or body != "ok":
            raise SlackClientError(
                f"Slack webhook returned {response.status}: {body}"
            )
