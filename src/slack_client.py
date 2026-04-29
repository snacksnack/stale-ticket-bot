import logging
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS_CODES = frozenset([429, 500, 502, 503, 504])


class SlackClientError(Exception):
    pass


class SlackTransientError(SlackClientError):
    pass


class SlackClient:
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(SlackTransientError),
        reraise=True,
    )
    def post_message(self, payload: dict) -> None:
        response = requests.post(self._webhook_url, json=payload, timeout=5)
        body = response.text
        logger.info(
            "slack webhook response",
            extra={
                "slack_status": response.status_code,
                "slack_response": body,
            },
        )
        if response.status_code in _TRANSIENT_STATUS_CODES:
            raise SlackTransientError(f"Slack webhook returned {response.status_code}: {body}")
        if response.status_code != 200 or body != "ok":
            raise SlackClientError(f"Slack webhook returned {response.status_code}: {body}")
