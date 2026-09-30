"""
Tests for `sql_database.SQLClient.SQLiteClient` (API as of 2026-09-29).

Contract:
  * `SQLiteClient(file_path, agent_name, agent_type, system_message)`
      - `file_path=None` -> env `DB_PATH` (default "sql_database/assistant.db").
      - Creates the schema from sql_database/sqlite_init.sql if needed (tables `messages`, `agents`).
      - `agent_name` is required (ValueError otherwise).
      - An existing agent is reused (`agent_id` = its row id); `agent_type`/`system_message` aren't needed.
      - A new agent is inserted from `agent_type` + `system_message` (ValueError if either is missing).
  * `save_messages(messages)` stores one row per message: raw_string = json.dumps(message),
    type = message["type"] or "message", agent_id = self.agent_id, datetime = UTC ISO timestamp.
  * `get_messages(seconds=86400)` returns this agent's messages from the last `seconds` seconds as the
    original dicts, oldest -> newest ([] if none), regardless of the machine's local timezone.

Every test uses a temp DB, and `DB_PATH` is pointed at a temp file so the project DB is never touched.
Run from the project root (the client reads sql_database/sqlite_init.sql relative to the cwd):
    uv run python -m pytest tests/test_sql.py
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

import sql_database.SQLClient as sql_module
from sql_database.SQLClient import SQLiteClient, SQLClient


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #
AGENT = "assistant_main"
SYSTEM_MESSAGE = "You are Alice, an AI secretary."
AGENT_TYPE = "assistant"  # must satisfy the schema CHECK(type IN ('assistant','subagent'))

SAMPLE_MESSAGES = [
    {"role": "user", "content": "System starts."},
    {"role": "assistant", "content": "Xin chào! How can I help?"},
    {"role": "user", "content": [
        {"type": "input_text", "text": "What's on my screen?"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
    ]},
    {"type": "function_call", "call_id": "call_1", "name": "wait", "arguments": '{"n": 5}'},
    {"type": "function_call_output", "call_id": "call_1", "output": "5 seconds have passed"},
]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _isolate_env_db_path(tmp_path, monkeypatch):
    """Safety net: a client built without file_path must never touch the project's DB."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "env.db"))


@pytest.fixture
def db_path(tmp_path):
    """A fresh, per-test SQLite file path."""
    return tmp_path / "messages.db"


@pytest.fixture
def make_client(db_path):
    """Factory for clients on the temp DB (defaults create/reuse AGENT)."""
    def _make(agent_name=AGENT, agent_type=AGENT_TYPE, system_message=SYSTEM_MESSAGE):
        return SQLiteClient(
            file_path=str(db_path),
            agent_name=agent_name,
            agent_type=agent_type,
            system_message=system_message,
        )
    return _make


@pytest.fixture
def client(make_client):
    return make_client()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _query(db_path, sql, params=()):
    con = sqlite3.connect(str(db_path))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _set_message_time(db_path, index, dt):
    """Overwrite the datetime of the index-th stored message (in insertion order)."""
    con = sqlite3.connect(str(db_path))
    try:
        ids = [r[0] for r in con.execute("SELECT id FROM messages ORDER BY id")]
        con.execute("UPDATE messages SET datetime = ? WHERE id = ?", (dt.isoformat(), ids[index]))
        con.commit()
    finally:
        con.close()


def _fake_local_datetime(utc_offset_hours):
    """A `datetime` class whose naive `now()` is the wall time of a fixed UTC offset."""
    offset = timedelta(hours=utc_offset_hours)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            utc_now = datetime.now(timezone.utc)
            if tz is None:
                return (utc_now + offset).replace(tzinfo=None)
            return utc_now.astimezone(tz)

    return FakeDatetime


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
def test_sqliteclient_is_sqlclient_subclass():
    assert issubclass(SQLiteClient, SQLClient)


def test_client_exposes_expected_api(client):
    assert callable(client.save_messages)
    assert callable(client.get_messages)
    assert isinstance(client.agent_id, int)


# --------------------------------------------------------------------------- #
# __init__: schema and agent
# --------------------------------------------------------------------------- #
def test_init_creates_schema(client, db_path):
    tables = {r[0] for r in _query(db_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"messages", "agents"} <= tables


def test_init_creates_new_agent(client, db_path):
    rows = _query(db_path, "SELECT id, name, system_message, type FROM agents")
    assert rows == [(client.agent_id, AGENT, SYSTEM_MESSAGE, AGENT_TYPE)]


def test_init_reuses_existing_agent(make_client, db_path):
    first = make_client()
    second = make_client(agent_type=None, system_message=None)  # info not needed for an existing agent
    assert second.agent_id == first.agent_id
    assert _query(db_path, "SELECT COUNT(*) FROM agents") == [(1,)]


def test_agents_get_distinct_ids(make_client):
    a = make_client(agent_name="agent_a", agent_type="assistant", system_message="A")
    b = make_client(agent_name="agent_b", agent_type="subagent", system_message="B")
    assert a.agent_id != b.agent_id


def test_init_without_agent_name_raises(db_path):
    with pytest.raises(ValueError):
        SQLiteClient(file_path=str(db_path))


@pytest.mark.parametrize("missing", ["agent_type", "system_message"])
def test_init_new_agent_without_info_raises(make_client, db_path, missing):
    with pytest.raises(ValueError):
        make_client(**{missing: None})
    assert _query(db_path, "SELECT COUNT(*) FROM agents") == [(0,)], "no agent row should be created"


def test_init_rejects_invalid_agent_type(make_client):
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        make_client(agent_type="boss")


def test_file_path_defaults_to_env_db_path(tmp_path, monkeypatch):
    env_path = tmp_path / "from_env.db"
    monkeypatch.setenv("DB_PATH", str(env_path))
    client = SQLiteClient(agent_name=AGENT, agent_type=AGENT_TYPE, system_message=SYSTEM_MESSAGE)
    assert client.file_path == str(env_path)
    assert env_path.exists()


def test_reopening_existing_db_keeps_messages(make_client):
    make_client().save_messages(SAMPLE_MESSAGES)
    reopened = make_client()  # schema init must not wipe or fail on an existing DB
    assert reopened.get_messages() == SAMPLE_MESSAGES


# --------------------------------------------------------------------------- #
# save_messages / get_messages
# --------------------------------------------------------------------------- #
def test_save_then_get_roundtrip(client):
    client.save_messages(SAMPLE_MESSAGES)
    assert client.get_messages() == SAMPLE_MESSAGES


def test_get_messages_empty_when_nothing_saved(client):
    assert client.get_messages() == []


def test_save_empty_list_is_a_noop(client, db_path):
    client.save_messages([])
    assert client.get_messages() == []
    assert _query(db_path, "SELECT COUNT(*) FROM messages") == [(0,)]


def test_multiple_saves_accumulate_in_order(client):
    first = [{"role": "user", "content": "first"}]
    second = [{"role": "assistant", "content": "second"}, {"role": "user", "content": "third"}]
    client.save_messages(first)
    client.save_messages(second)
    assert client.get_messages() == first + second


def test_saved_rows_populate_columns(client, db_path):
    client.save_messages(SAMPLE_MESSAGES)
    rows = _query(db_path, "SELECT raw_string, type, agent_id, datetime FROM messages ORDER BY id")
    assert len(rows) == len(SAMPLE_MESSAGES), "one row per message"

    assert [json.loads(r[0]) for r in rows] == SAMPLE_MESSAGES
    assert [r[1] for r in rows] == [m.get("type", "message") for m in SAMPLE_MESSAGES]
    assert all(r[2] == client.agent_id for r in rows)

    now = datetime.now(timezone.utc)
    for r in rows:
        stamp = datetime.fromisoformat(r[3])
        assert stamp.utcoffset() == timedelta(0), f"datetime should be stored in UTC, got {r[3]!r}"
        assert abs(now - stamp) < timedelta(minutes=1)


def test_messages_are_isolated_per_agent(make_client):
    a = make_client(agent_name="agent_a", agent_type="assistant", system_message="A")
    b = make_client(agent_name="agent_b", agent_type="subagent", system_message="B")
    msgs_a = [{"role": "user", "content": "for A"}]
    msgs_b = [{"role": "user", "content": "for B"}]
    a.save_messages(msgs_a)
    b.save_messages(msgs_b)
    assert a.get_messages() == msgs_a
    assert b.get_messages() == msgs_b


# --------------------------------------------------------------------------- #
# Time window
# --------------------------------------------------------------------------- #
def test_get_messages_excludes_messages_older_than_window(client, db_path):
    older = {"role": "user", "content": "old message"}
    newer = {"role": "assistant", "content": "recent message"}
    client.save_messages([older, newer])
    _set_message_time(db_path, 0, datetime.now(timezone.utc) - timedelta(days=2))

    assert client.get_messages(seconds=60 * 60) == [newer], "a 1-hour window should exclude a 2-day-old message"
    assert client.get_messages(seconds=60 * 60 * 24 * 7) == [older, newer], "a 1-week window should include both"


@pytest.mark.parametrize("utc_offset_hours", [7, -5], ids=["local=UTC+7", "local=UTC-5"])
def test_time_window_ignores_local_timezone(client, db_path, monkeypatch, utc_offset_hours):
    """Timestamps are stored in UTC, so the window start must be computed in UTC too."""
    three_hours_old = {"role": "user", "content": "three hours ago"}
    just_now = {"role": "assistant", "content": "just now"}
    client.save_messages([three_hours_old, just_now])
    _set_message_time(db_path, 0, datetime.now(timezone.utc) - timedelta(hours=3))

    monkeypatch.setattr(sql_module, "datetime", _fake_local_datetime(utc_offset_hours))
    assert client.get_messages(seconds=60 * 60) == [just_now]
