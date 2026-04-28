import logging
import requests

logger = logging.getLogger(__name__)


class SlackClientError(Exception):
    pass


class SlackClient:
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    def post_message(self, payload: dict) -> None:
        response = requests.post(self._webhook_url, json=payload)
        body = response.text
        logger.info(
            "slack webhook response",
            extra={"slack_status": response.status_code, "slack_response": body},
        )
        if response.status_code != 200 or body != "ok":
            raise SlackClientError(
                f"Slack webhook returned {response.status_code}: {body}"
            )
