"""
Contract tests for `sql_database.SQLClient.SQLiteClient` (updated for the revised plan).

New plan reflected here:
  * `SQLiteClient(file_path)` initialises the database, creating the schema from
    `sqlite_init.sql` (tables `messages` and `agents`).
  * Agents are created explicitly with `create_agent(name, type, system_message)`.
  * `save_messages(messages, agent_name)` and `get_messages(agent_name, seconds)`
    **raise `ValueError`** when `agent_name` has not been created.
  * `save_messages` stores each message as `raw_string = json.dumps(message)`, a `type`
    (`message["type"]`, else `"message"`), an `agent_id`, and a UTC timestamp.
  * `get_messages` returns the agent's messages within the last `seconds` seconds as a
    list of the original dicts (parsed from `raw_string`), oldest -> newest; `[]` if none.

These are contract tests: they define the intended behaviour. Where the current
implementation doesn't yet satisfy the contract they will fail/error — see the summary
returned with this change for the specific implementation issues found.

Run:  uv run python -m pytest tests/test_sql.py
"""
import os
import sys
import json
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

# Make the project root importable no matter how pytest is invoked.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sql_database.SQLClient import SQLiteClient, SQLClient


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #
AGENT = "assistant_main"
SYSTEM_MESSAGE = "You are Alice, an AI secretary."
AGENT_TYPE = "assistant"  # must satisfy the schema CHECK(type IN ('assistant','subagent'))

SAMPLE_MESSAGES = [
    {"role": "user", "content": "System starts."},
    {"role": "assistant", "content": "Hello, how can I help?"},
    {"type": "function_call", "call_id": "call_1", "name": "wait", "arguments": '{"n": 5}'},
    {"type": "function_call_output", "call_id": "call_1", "output": "5 seconds have passed"},
]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def db_path(tmp_path):
    """A fresh, per-test SQLite file path."""
    return tmp_path / "messages.db"


@pytest.fixture
def client(db_path):
    """A SQLiteClient pointed at the temp DB (its __init__ is expected to build the schema)."""
    return SQLiteClient(file_path=str(db_path))


@pytest.fixture
def client_with_agent(client):
    """A client that already has AGENT registered."""
    client.create_agent(name=AGENT, type=AGENT_TYPE, system_message=SYSTEM_MESSAGE)
    return client


# --------------------------------------------------------------------------- #
# DB inspection helpers (tolerate a not-yet-created schema)
# --------------------------------------------------------------------------- #
def _query(db_path, sql, params=()):
    try:
        con = sqlite3.connect(str(db_path))
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()
    except sqlite3.OperationalError:
        return []


def _table_names(db_path):
    return {r[0] for r in _query(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}


def _backdate_earliest_message(db_path, dt_iso):
    """Set the oldest message's timestamp, to exercise the time window."""
    try:
        con = sqlite3.connect(str(db_path))
        try:
            con.execute(
                "UPDATE messages SET datetime = ? WHERE id = (SELECT MIN(id) FROM messages)",
                (dt_iso,),
            )
            con.commit()
        finally:
            con.close()
    except sqlite3.OperationalError:
        pass


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
def test_sqliteclient_is_sqlclient_subclass():
    assert issubclass(SQLiteClient, SQLClient)


def test_client_exposes_expected_methods(client):
    assert callable(client.create_agent)
    assert callable(client.save_messages)
    assert callable(client.get_messages)


# --------------------------------------------------------------------------- #
# Schema / agents
# --------------------------------------------------------------------------- #
def test_init_creates_schema(client, db_path):
    """Constructing the client initialises the DB with the messages and agents tables."""
    tables = _table_names(db_path)
    assert "messages" in tables, "__init__ should create the 'messages' table"
    assert "agents" in tables, "__init__ should create the 'agents' table"


def test_create_agent_adds_row(client, db_path):
    """create_agent inserts a row into agents with the given name/system_message/type."""
    client.create_agent(name=AGENT, type=AGENT_TYPE, system_message=SYSTEM_MESSAGE)

    rows = _query(db_path, "SELECT name, system_message, type FROM agents WHERE name = ?", (AGENT,))
    assert rows == [(AGENT, SYSTEM_MESSAGE, AGENT_TYPE)]


# --------------------------------------------------------------------------- #
# Unknown-agent handling
# --------------------------------------------------------------------------- #
def test_save_messages_unknown_agent_raises(client):
    with pytest.raises(ValueError):
        client.save_messages(SAMPLE_MESSAGES, "nonexistent_agent")


def test_get_messages_unknown_agent_raises(client):
    with pytest.raises(ValueError):
        client.get_messages("nonexistent_agent")


# --------------------------------------------------------------------------- #
# save / get behaviour
# --------------------------------------------------------------------------- #
def test_save_then_get_roundtrip(client_with_agent):
    client_with_agent.save_messages(SAMPLE_MESSAGES, AGENT)
    result = client_with_agent.get_messages(AGENT)

    assert isinstance(result, list), "get_messages should return a list"
    assert result == SAMPLE_MESSAGES, "get_messages should return the saved messages, oldest first"


def test_get_messages_empty_for_known_agent_without_messages(client_with_agent):
    assert client_with_agent.get_messages(AGENT) == []


def test_messages_are_isolated_per_agent(client):
    client.create_agent(name="agent_a", type="assistant", system_message="A")
    client.create_agent(name="agent_b", type="subagent", system_message="B")

    msgs_a = [{"role": "user", "content": "for A"}]
    msgs_b = [{"role": "user", "content": "for B"}]
    client.save_messages(msgs_a, "agent_a")
    client.save_messages(msgs_b, "agent_b")

    assert client.get_messages("agent_a") == msgs_a
    assert client.get_messages("agent_b") == msgs_b


def test_multiple_saves_accumulate_in_order(client_with_agent):
    first = [{"role": "user", "content": "first"}]
    second = [
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    client_with_agent.save_messages(first, AGENT)
    client_with_agent.save_messages(second, AGENT)

    assert client_with_agent.get_messages(AGENT) == first + second


def test_saved_rows_populate_columns(client_with_agent, db_path):
    """Each message becomes a row with the derived `type` and a single shared `agent_id`."""
    client_with_agent.save_messages(SAMPLE_MESSAGES, AGENT)

    rows = _query(db_path, "SELECT type, agent_id, datetime FROM messages ORDER BY id")
    assert len(rows) == len(SAMPLE_MESSAGES), "one messages row per message"

    stored_types = [r[0] for r in rows]
    expected_types = [m.get("type", "message") for m in SAMPLE_MESSAGES]
    assert stored_types == expected_types, "type column should be message['type'] or 'message'"

    agent_ids = [r[1] for r in rows]
    assert all(a is not None for a in agent_ids) and len(set(agent_ids)) == 1, \
        "all rows should link to the one agent's id"

    assert all(r[2] for r in rows), "every row should have a datetime"


def test_get_messages_excludes_messages_older_than_window(client_with_agent, db_path):
    """
    get_messages(..., seconds=N) returns only messages from the last N seconds.

    Assumes timestamps are stored and compared consistently in UTC.
    """
    older = {"role": "user", "content": "old message"}
    newer = {"role": "assistant", "content": "recent message"}
    client_with_agent.save_messages([older, newer], AGENT)

    # Push the oldest row two days into the past (UTC).
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    _backdate_earliest_message(db_path, two_days_ago)

    within_hour = client_with_agent.get_messages(AGENT, seconds=60 * 60)
    assert isinstance(within_hour, list)
    assert within_hour == [newer], "a 1-hour window should exclude the 2-day-old message"

    within_week = client_with_agent.get_messages(AGENT, seconds=60 * 60 * 24 * 7)
    assert within_week == [older, newer], "a 1-week window should include both messages"
