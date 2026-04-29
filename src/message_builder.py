from datetime import datetime, timezone

# Slack Block Kit hard limit is 50 blocks.
# Formula: 1 header + 1 divider + n sections + (n-1) inter-ticket dividers + 1 footer = 2n+2.
# Cap at 23 so that adding a "and N more" context block keeps the total at 49.
_MAX_DISPLAYED = 23


def build_stale_ticket_message(tickets: list, stale_days: int) -> dict | None:
    if not tickets:
        return None

    total = len(tickets)
    displayed = tickets[:_MAX_DISPLAYED]
    noun = "ticket" if total == 1 else "tickets"
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Stale Ticket Reminder: {total} {noun}",
                "emoji": False,
            },
        },
        {"type": "divider"},
    ]

    for i, ticket in enumerate(displayed):
        assignee = ticket["assignee"] or "Unassigned"
        text = (
            f"*<{ticket['url']}|{ticket['key']}>*\n"
            f"{ticket['summary']}\n"
            f"*Status:* {ticket['status']}  |  "
            f"*Stale:* {ticket['days_stale']} days  |  "
            f"*Assignee:* {assignee}"
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Ticket",
                    "emoji": False,
                },
                "url": ticket["url"],
            },
        })
        if i < len(displayed) - 1:
            blocks.append({"type": "divider"})

    if total > _MAX_DISPLAYED:
        hidden = total - _MAX_DISPLAYED
        noun_hidden = "ticket" if hidden == 1 else "tickets"
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"...and {hidden} more {noun_hidden}"}],
        })

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Tickets inactive for >{stale_days} days  |  {timestamp}",
            }
        ],
    })

    return {"blocks": blocks}
