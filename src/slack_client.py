import logging
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Slack Web API, not an incoming webhook. The bot's webhook was revoked on the
# Slack side in July 2026 and answered 404 "no_service" for two months while
# nothing else in this stack noticed (RC1-436). The incident summarizer's bot
# token is used daily and posts through the same call, so the two share it.
_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
_TRANSIENT_STATUS_CODES = frozenset([429, 500, 502, 503, 504])
_TRANSIENT_ERRORS = frozenset(["ratelimited", "internal_error", "service_unavailable"])


class SlackClientError(Exception):
    pass


class SlackTransientError(SlackClientError):
    pass


class SlackClient:
    def __init__(self, bot_token: str, channel_id: str):
        self._bot_token = bot_token
        self._channel_id = channel_id

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(SlackTransientError),
        reraise=True,
    )
    def post_message(self, payload: dict) -> str:
        """Post a Block Kit payload to the channel; return the message ts."""
        response = requests.post(
            _POST_MESSAGE_URL,
            json={"channel": self._channel_id, **payload},
            headers={"Authorization": f"Bearer {self._bot_token}"},
            timeout=5,
        )
        body = _parse_body(response)
        logger.info(
            "slack api response",
            extra={
                "slack_status": response.status_code,
                "slack_ok": body.get("ok"),
                "slack_error": body.get("error"),
            },
        )
        if response.status_code in _TRANSIENT_STATUS_CODES:
            raise SlackTransientError(f"Slack API returned {response.status_code}: {response.text}")
        if response.status_code != 200:
            raise SlackClientError(f"Slack API returned {response.status_code}: {response.text}")
        if not body.get("ok"):
            error = body.get("error", "unknown_error")
            if error in _TRANSIENT_ERRORS:
                raise SlackTransientError(f"Slack API error: {error}")
            raise SlackClientError(f"Slack API error: {error}")
        return body.get("ts", "")


def _parse_body(response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
