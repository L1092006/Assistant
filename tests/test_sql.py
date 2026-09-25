"""
TDD contract tests for `sql_database.SQLClient.SQLiteClient`.

STATUS: `SQLiteClient` is currently a stub — `__init__`, `save_messages` and
`get_messages` are all `pass`. These are **specification / TDD tests**: the two
interface tests pass now, but every behavioural test below is expected to FAIL
until `SQLiteClient` is implemented. They encode the intended contract inferred
from the docstrings in `sql_database/SQLClient.py` and the schema in
`sql_database/sqlite_init.sql`.

Assumed contract (adjust the implementation — or these tests — if the intent differs):

`SQLiteClient(file_path: str)`
    - Opens/creates a SQLite database at `file_path` and ensures the schema from
      `sqlite_init.sql` exists: tables `messages` and `agents`.

`save_messages(messages: list[dict], agent_name: str) -> None`
    - Appends one row to `messages` per message dict:
        * `raw_string` = `json.dumps(message)`
        * `type`       = the message's type (`message["type"]` for tool items, or a
                          non-empty derived type such as "message" for role messages)
        * `agent_id`   = the id of the agent named `agent_name` (created/looked up as
                          needed; the same name maps to a single `agents` row)
        * `datetime`   = insertion time (UTC, via the column's CURRENT_TIMESTAMP default)
    - Multiple calls accumulate.

`get_messages(agent_name: str, seconds: int = 86400) -> list[dict]`
    - Returns the messages saved for `agent_name` whose `datetime` is within the last
      `seconds` seconds, as a list of the original message dicts (parsed from
      `raw_string`), ordered oldest -> newest. Returns `[]` when there are none.

Run:  uv run python -m pytest tests/test_sql.py
"""
import os
import sys
import json
import sqlite3

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

SAMPLE_MESSAGES = [
    {"role": "user", "content": "System starts."},
    {"role": "assistant", "content": "Hello, how can I help?"},
    {"type": "function_call", "call_id": "call_1", "name": "wait", "arguments": '{"n": 5}'},
    {"type": "function_call_output", "call_id": "call_1", "output": "5 seconds have passed"},
]

MESSAGES_B = [
    {"role": "user", "content": "A message for a different agent"},
]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def db_path(tmp_path):
    """A fresh, per-test SQLite file path (nothing is created until the client does)."""
    return tmp_path / "messages.db"


@pytest.fixture
def client(db_path):
    """A SQLiteClient pointed at the temp DB."""
    return SQLiteClient(file_path=str(db_path))


# --------------------------------------------------------------------------- #
# Helpers (read the DB directly to verify persistence / set up time windows).
# They tolerate a not-yet-created schema so the stub fails on a clean behavioural
# assertion rather than raising sqlite3.OperationalError.
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
    rows = _query(db_path, "SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in rows}


def _backdate_earliest_message(db_path, modifier="-2 days"):
    """Move the oldest stored message's timestamp into the past, to test the time window."""
    try:
        con = sqlite3.connect(str(db_path))
        try:
            con.execute(
                "UPDATE messages SET datetime = datetime('now', ?) "
                "WHERE id = (SELECT MIN(id) FROM messages)",
                (modifier,),
            )
            con.commit()
        finally:
            con.close()
    except sqlite3.OperationalError:
        pass


# --------------------------------------------------------------------------- #
# Interface tests (pass now)
# --------------------------------------------------------------------------- #
def test_sqliteclient_is_sqlclient_subclass():
    assert issubclass(SQLiteClient, SQLClient)


def test_methods_are_callable(client):
    assert callable(client.save_messages)
    assert callable(client.get_messages)


# --------------------------------------------------------------------------- #
# Behavioural contract tests (fail until SQLiteClient is implemented)
# --------------------------------------------------------------------------- #
def test_init_creates_schema(client, db_path):
    """Constructing the client should create the `messages` and `agents` tables."""
    tables = _table_names(db_path)
    assert "messages" in tables, "SQLiteClient.__init__ should create the 'messages' table"
    assert "agents" in tables, "SQLiteClient.__init__ should create the 'agents' table"


def test_save_then_get_roundtrip(client):
    """Messages saved for an agent are returned by get_messages, unchanged and in order."""
    client.save_messages(SAMPLE_MESSAGES, AGENT)
    result = client.get_messages(AGENT)

    assert isinstance(result, list), "get_messages should return a list"
    assert result == SAMPLE_MESSAGES, "get_messages should return the saved messages, oldest first"


def test_get_messages_returns_empty_list_when_none(client):
    """An agent with no stored messages yields an empty list (not None)."""
    result = client.get_messages("no_such_agent")
    assert result == [], "get_messages should return [] when the agent has no messages"


def test_messages_are_isolated_per_agent(client):
    """get_messages(agent) returns only that agent's messages."""
    client.save_messages(SAMPLE_MESSAGES, AGENT)
    client.save_messages(MESSAGES_B, "other_agent")

    assert client.get_messages(AGENT) == SAMPLE_MESSAGES
    assert client.get_messages("other_agent") == MESSAGES_B


def test_multiple_saves_accumulate_in_order(client):
    """Successive save_messages calls append; get_messages returns them oldest -> newest."""
    first = [{"role": "user", "content": "first"}]
    second = [
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    client.save_messages(first, AGENT)
    client.save_messages(second, AGENT)

    assert client.get_messages(AGENT) == first + second


def test_saved_rows_populate_type_and_agent_columns(client, db_path):
    """
    Each saved message becomes one `messages` row with a non-empty `type` and a valid
    `agent_id`, and the agent name maps to exactly one `agents` row.
    """
    client.save_messages(SAMPLE_MESSAGES, AGENT)

    rows = _query(db_path, "SELECT type, agent_id FROM messages ORDER BY id")
    assert len(rows) == len(SAMPLE_MESSAGES), "one messages row should be stored per message"

    types = [r[0] for r in rows]
    agent_ids = [r[1] for r in rows]
    assert all(isinstance(t, str) and t for t in types), "every row needs a non-empty 'type'"
    assert all(a is not None for a in agent_ids), "every row needs an 'agent_id'"
    assert len(set(agent_ids)) == 1, "all messages for one agent should link to the same agent_id"

    agent_rows = _query(db_path, "SELECT COUNT(*) FROM agents WHERE name = ?", (AGENT,))
    assert agent_rows and agent_rows[0][0] == 1, "the agent name should map to exactly one agents row"


def test_get_messages_excludes_messages_older_than_window(client, db_path):
    """
    get_messages(..., seconds=N) returns only messages from the last N seconds.

    NOTE: this is the most implementation-coupled test — it assumes timestamps are stored
    in the `datetime` column in UTC (matching the schema's CURRENT_TIMESTAMP default) so
    that SQLite's datetime() comparison drives the window.
    """
    older = {"role": "user", "content": "old message"}
    newer = {"role": "assistant", "content": "recent message"}
    client.save_messages([older, newer], "agent_time")

    # Push the first (oldest) row two days into the past.
    _backdate_earliest_message(db_path, "-2 days")

    within_hour = client.get_messages("agent_time", seconds=60 * 60)
    assert isinstance(within_hour, list), "get_messages should return a list"
    assert within_hour == [newer], "a 1-hour window should exclude the 2-day-old message"

    within_week = client.get_messages("agent_time", seconds=60 * 60 * 24 * 7)
    assert within_week == [older, newer], "a 1-week window should include both messages"
