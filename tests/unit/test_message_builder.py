from unittest.mock import patch

from message_builder import build_stale_ticket_message, _MAX_DISPLAYED

TICKET = {
    "key": "RC1-42",
    "summary": "Fix the broken thing",
    "status": "In Progress",
    "assignee": "Jane Doe",
    "url": "https://jira.example.com/browse/RC1-42",
    "days_stale": 10,
}

TICKET_2 = {
    "key": "RC1-99",
    "summary": "Another stale thing",
    "status": "To Do",
    "assignee": "John Smith",
    "url": "https://jira.example.com/browse/RC1-99",
    "days_stale": 20,
}


def _fixed_dt(mock_dt):
    mock_dt.now.return_value.strftime.return_value = "2026-04-28 09:00 UTC"


def test_empty_tickets_returns_none():
    assert build_stale_ticket_message([], 7) is None


@patch("message_builder.datetime")
def test_single_ticket_uses_singular_noun(mock_dt):
    _fixed_dt(mock_dt)
    result = build_stale_ticket_message([TICKET], 7)
    header = result["blocks"][0]
    assert header["text"]["text"] == "Stale Ticket Reminder: 1 ticket"


@patch("message_builder.datetime")
def test_multiple_tickets_uses_plural_noun(mock_dt):
    _fixed_dt(mock_dt)
    result = build_stale_ticket_message([TICKET, TICKET_2], 7)
    header = result["blocks"][0]
    assert header["text"]["text"] == "Stale Ticket Reminder: 2 tickets"


@patch("message_builder.datetime")
def test_single_ticket_block_structure(mock_dt):
    _fixed_dt(mock_dt)
    result = build_stale_ticket_message([TICKET], 7)
    blocks = result["blocks"]

    # header, divider, section, context — no inter-ticket divider
    assert blocks[0]["type"] == "header"
    assert blocks[1]["type"] == "divider"
    assert blocks[2]["type"] == "section"
    assert blocks[-1]["type"] == "context"


@patch("message_builder.datetime")
def test_single_ticket_section_contains_ticket_fields(mock_dt):
    _fixed_dt(mock_dt)
    result = build_stale_ticket_message([TICKET], 7)
    section_text = result["blocks"][2]["text"]["text"]

    assert "RC1-42" in section_text
    assert "Fix the broken thing" in section_text
    assert "In Progress" in section_text
    assert "Jane Doe" in section_text
    assert "10 days" in section_text


@patch("message_builder.datetime")
def test_multiple_tickets_has_divider_between_not_after_last(mock_dt):
    _fixed_dt(mock_dt)
    result = build_stale_ticket_message([TICKET, TICKET_2], 7)
    blocks = result["blocks"]

    # header, divider, section1, divider, section2, context
    section_indices = [i for i, b in enumerate(blocks) if b["type"] == "section"]
    assert len(section_indices) == 2

    between = blocks[section_indices[0] + 1]
    assert between["type"] == "divider"

    after_last = blocks[section_indices[1] + 1]
    assert after_last["type"] == "context"


@patch("message_builder.datetime")
def test_null_assignee_shows_unassigned(mock_dt):
    _fixed_dt(mock_dt)
    ticket = dict(TICKET, assignee=None)
    result = build_stale_ticket_message([ticket], 7)
    section_text = result["blocks"][2]["text"]["text"]

    assert "Unassigned" in section_text


@patch("message_builder.datetime")
def test_truncates_at_max_displayed_and_shows_overflow_count(mock_dt):
    _fixed_dt(mock_dt)
    tickets = [dict(TICKET, key=f"RC1-{i}") for i in range(_MAX_DISPLAYED + 5)]
    result = build_stale_ticket_message(tickets, 7)
    blocks = result["blocks"]

    sections = [b for b in blocks if b["type"] == "section"]
    assert len(sections) == _MAX_DISPLAYED

    overflow_block = blocks[-2]  # second-to-last, before footer
    assert overflow_block["type"] == "context"
    assert "5 more tickets" in overflow_block["elements"][0]["text"]


@patch("message_builder.datetime")
def test_block_count_never_exceeds_slack_limit(mock_dt):
    _fixed_dt(mock_dt)
    tickets = [dict(TICKET, key=f"RC1-{i}") for i in range(_MAX_DISPLAYED + 10)]
    result = build_stale_ticket_message(tickets, 7)
    assert len(result["blocks"]) <= 50


@patch("message_builder.datetime")
def test_stale_days_appears_in_footer(mock_dt):
    _fixed_dt(mock_dt)
    result = build_stale_ticket_message([TICKET], 14)
    context_text = result["blocks"][-1]["elements"][0]["text"]

    assert ">14 days" in context_text
    assert "2026-04-28 09:00 UTC" in context_text
