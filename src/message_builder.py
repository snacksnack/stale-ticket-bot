from datetime import datetime, timezone


def build_stale_ticket_message(tickets: list, stale_days: int) -> dict | None:
    if not tickets:
        return None

    count = len(tickets)
    noun = "ticket" if count == 1 else "tickets"
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Stale Ticket Reminder: {count} {noun}",
                "emoji": False,
            },
        },
        {"type": "divider"},
    ]

    for i, ticket in enumerate(tickets):
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
        if i < count - 1:
            blocks.append({"type": "divider"})

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
