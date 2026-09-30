"""
Contract tests for `MessageList.MessageList`.

Design decisions encoded here (confirmed 2026-09-29):
  * `__init__` starts empty: it does NOT load history from SQL and takes no seed messages.
  * `get_messages()` returns a copy of the original messages.
  * `add_messages(msgs)` appends `msgs` to the original list, adds each message's processed
    JSON string to `modified_messages` and its extracted files to `files_modified_messages`,
    and saves the new messages with `sql_client.save_messages(msgs)`.
  * When the window goes over `max_tokens_messages` tokens or `max_files` files, `_summarize`
    keeps the newest messages that fit in HALF of each budget (always at least the newest
    one), cuts the window at the first message that doesn't fit, and sends every dropped
    message (text + files) to the summarize agent.
  * The summarizer's output is APPENDED to `summary` (the old summary is only context).
  * If the summary gets longer than `max_tokens_summary`, the split agent shortens it and the
    leftover memories go to `memory_client.add(..., collection_name=f"{agent_name}-recent")`.

External dependencies are faked: SQLiteClient (no DB file is created), Runner (no LLM calls)
and the memory client. Failures point at the MessageList bugs listed in REPORT.md.

Run:  uv run python -m pytest tests/test_message_list.py
"""
import os
import sys
import json
import asyncio
import importlib
import importlib.util
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Module import
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def mlm():
    """
    The MessageList module.

    Under pytest, `tests/` comes before the project root on sys.path, so `helpers` resolves to
    tests/helpers.py and MessageList's `from helpers import count` fails. Put the project-root
    helpers module in sys.modules while importing, then restore whatever was there.
    Imported in a fixture so an import error fails these tests only, not the whole collection.
    """
    if "MessageList" in sys.modules:
        return sys.modules["MessageList"]
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)

    spec = importlib.util.spec_from_file_location("helpers", os.path.join(_ROOT, "helpers.py"))
    root_helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(root_helpers)

    previous = sys.modules.get("helpers")
    sys.modules["helpers"] = root_helpers
    try:
        return importlib.import_module("MessageList")
    finally:
        if previous is None:
            sys.modules.pop("helpers", None)
        else:
            sys.modules["helpers"] = previous


# --------------------------------------------------------------------------- #
# Fakes / fixtures
# --------------------------------------------------------------------------- #
class FakeRunner:
    """
    Stands in for `agents.Runner`: records inputs and returns canned structured outputs.

    Like the real SDK, `final_output` is an instance of the agent's pydantic `output_type`
    (attribute access, not a dict).
    """

    def __init__(self, mlm):
        self._ML = mlm.MessageList
        self.summaries = []  # queued outputs for the summarize agent (FIFO)
        self.default_summary = "summary"
        self.split_result = ("short summary", ["memory one", "memory two"])
        self.summarize_calls = []  # the `input` given to the summarize agent, per call
        self.split_calls = []  # the `input` given to the split agent, per call

    async def run(self, starting_agent, input, **kwargs):
        if starting_agent.output_type is self._ML.SplitOutput:
            self.split_calls.append(input)
            new_summary, memories = self.split_result
            return SimpleNamespace(final_output=self._ML.SplitOutput(new_summary=new_summary, memories=list(memories)))
        self.summarize_calls.append(input)
        text = self.summaries.pop(0) if self.summaries else self.default_summary
        return SimpleNamespace(final_output=self._ML.SummarizeOutput(summary=text))


@pytest.fixture
def env(monkeypatch):
    """Provider settings read by MessageList.__init__."""
    monkeypatch.setenv("PROVIDER_URL", "http://localhost:9/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("MODEL", "env-model")


@pytest.fixture
def prompts(mlm, monkeypatch):
    """Placeholder prompts for keys prompts.py doesn't define yet (covered by test_init_with_real_prompts)."""
    for key in ("summarization", "split"):
        if key not in mlm.system_prompts:
            monkeypatch.setitem(mlm.system_prompts, key, f"test {key} prompt")


@pytest.fixture
def sql_cls(mlm, monkeypatch):
    """Replace SQLiteClient so no database file is touched. `sql_cls.return_value` is the instance."""
    cls = MagicMock(name="SQLiteClient")
    cls.return_value.get_messages.return_value = []
    monkeypatch.setattr(mlm, "SQLiteClient", cls)
    return cls


@pytest.fixture
def runner(mlm, monkeypatch):
    fake = FakeRunner(mlm)
    monkeypatch.setattr(mlm, "Runner", fake)
    return fake


@pytest.fixture
def make_list(mlm, env, prompts, sql_cls, runner):
    """Factory for MessageList objects wired to the fakes above."""
    def _make(**kwargs):
        kwargs.setdefault("memory_client", MagicMock(name="MemoryClient"))
        return mlm.MessageList(**kwargs)
    return _make


@pytest.fixture
def ml(make_list):
    return make_list(max_tokens=100, max_files=4)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _run(coro):
    return asyncio.run(coro)


def _msg(i, words=10):
    """A user message whose processed JSON is 3 + `words` tokens (count() splits on spaces)."""
    return {"role": "user", "content": " ".join([f"msg{i:02d}"] * words)}


def _image_part(i):
    return {"type": "input_image", "image_url": f"data:image/png;base64,IMG{i:02d}"}


def _img_msg(i):
    """A small user message carrying one image."""
    return {"role": "user", "content": [{"type": "input_text", "text": f"img{i:02d}"}, _image_part(i)]}


def _tag(message):
    """The msgNN / imgNN tag of a message dict or of its processed JSON string."""
    if isinstance(message, str):
        message = json.loads(message)
    content = message["content"]
    text = content if isinstance(content, str) else content[0]["text"]
    return text.split()[0]


def _summarize_input(call_input):
    """Split the input given to the summarize agent into (prompt text, file parts)."""
    assert isinstance(call_input, list) and len(call_input) == 1, "summarize agent should get one message"
    message = call_input[0]
    assert message["role"] == "user"
    parts = message["content"]
    assert isinstance(parts, list) and parts[0]["type"] == "input_text", \
        "content should be [input_text prompt, *file parts]"
    return parts[0]["text"], parts[1:]


def _saved_batches(sql_cls):
    """The message lists passed to sql_client.save_messages, one per call."""
    return [c.args[0] if c.args else c.kwargs["messages"]
            for c in sql_cls.return_value.save_messages.call_args_list]


def _memory_add_args(memory_client):
    c = memory_client.add.call_args
    chunks = c.args[0] if c.args else c.kwargs["chunks"]
    collection = c.kwargs["collection_name"] if "collection_name" in c.kwargs else c.args[1]
    return chunks, collection


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
def test_init_with_real_prompts(mlm, env, sql_cls):
    """__init__ reads system_prompts['summarization'] and ['split']; both must exist."""
    missing = [k for k in ("summarization", "split") if k not in mlm.system_prompts]
    assert not missing, f"prompts.system_prompts is missing {missing}; MessageList.__init__ raises KeyError"
    mlm.MessageList(memory_client=MagicMock())


def test_init_splits_token_budget(make_list):
    ml = make_list(max_tokens=100, max_files=4)
    assert ml.max_tokens_messages == 70
    assert ml.max_tokens_summary == 30
    assert ml.max_files == 4


def test_init_starts_empty(make_list):
    ml = make_list()
    assert ml.get_messages() == []
    assert ml.modified_messages == []
    assert ml.files_modified_messages == []
    assert ml.summary == ""


def test_init_registers_agent_with_sql_client(make_list, sql_cls):
    make_list(agent_name="Bob", agent_type="subagent", system_message="You are Bob.")
    sql_cls.assert_called_once()
    kwargs = sql_cls.call_args.kwargs
    assert kwargs.get("agent_name") == "Bob"
    assert kwargs.get("agent_type") == "subagent"
    assert kwargs.get("system_message") == "You are Bob."


def test_init_does_not_load_history_from_sql(make_list, sql_cls):
    sql_cls.return_value.get_messages.return_value = [_msg(0)]
    ml = make_list()
    sql_cls.return_value.get_messages.assert_not_called()
    assert ml.get_messages() == []


def test_summarization_model_argument_overrides_env(make_list):
    ml = make_list(summarization_model="custom-model")
    assert ml.summarize_agent.model.model == "custom-model"
    assert ml.split_agent.model.model == "custom-model"


def test_summarization_model_defaults_to_env(make_list):
    ml = make_list()
    assert ml.summarize_agent.model.model == "env-model"
    assert ml.split_agent.model.model == "env-model"


def test_agents_use_structured_outputs_and_prompts(mlm, make_list):
    ml = make_list()
    assert ml.summarize_agent.output_type is mlm.MessageList.SummarizeOutput
    assert ml.split_agent.output_type is mlm.MessageList.SplitOutput
    assert ml.summarize_agent.instructions == mlm.system_prompts["summarization"]
    assert ml.split_agent.instructions == mlm.system_prompts["split"]


# --------------------------------------------------------------------------- #
# _process_message
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("message", [
    {"role": "user", "content": "hello there"},
    {"role": "assistant", "content": "hi, how can I help?"},
    {"type": "function_call_output", "call_id": "call_1", "output": "5 seconds have passed"},
])
def test_process_message_simple(mlm, ml, message):
    num_tokens, num_files, files, processed = ml._process_message(message)
    assert json.loads(processed) == message
    assert num_tokens == mlm.count(processed)
    assert num_files == 0
    assert files == []


def test_process_message_strips_extra_fields_from_role_messages(ml):
    item = {
        "id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": "hi", "annotations": []}],
    }
    _, _, _, processed = ml._process_message(item)
    assert json.loads(processed) == {"role": "assistant", "content": item["content"]}


def test_process_message_extracts_files_from_user_content(ml):
    num_tokens, num_files, files, processed = ml._process_message(_img_msg(0))
    assert num_files == 1
    assert files == [_image_part(0)]

    parts = json.loads(processed)["content"]
    assert parts[0] == {"type": "input_text", "text": "img00"}
    assert len(parts) == 2 and parts[1]["type"] == "input_text", "the file should be replaced by a text placeholder"
    assert "IMG00" not in processed, "file data must not stay in the processed message"


def test_process_message_function_call_keeps_core_fields(ml):
    item = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "wait",
            "arguments": '{"n": 5}', "status": "completed"}
    _, num_files, _, processed = ml._process_message(item)
    assert json.loads(processed) == {"type": "function_call", "call_id": "call_1", "name": "wait", "arguments": '{"n": 5}'}
    assert num_files == 0


def test_process_message_extracts_files_from_function_call_output(ml):
    item = {"type": "function_call_output", "call_id": "call_2",
            "output": [{"type": "input_text", "text": "screenshot:"}, _image_part(7)]}
    _, num_files, files, processed = ml._process_message(item)
    assert num_files == 1
    assert files == [_image_part(7)]

    new = json.loads(processed)
    assert new["type"] == "function_call_output" and new["call_id"] == "call_2"
    assert new["output"][0] == {"type": "input_text", "text": "screenshot:"}
    assert len(new["output"]) == 2 and new["output"][1]["type"] == "input_text"
    assert "IMG07" not in processed


def test_process_message_leaves_other_items_unchanged(ml):
    item = {"type": "reasoning", "id": "rs_1", "summary": []}
    _, num_files, files, processed = ml._process_message(item)
    assert json.loads(processed) == item
    assert (num_files, files) == (0, [])


def test_process_message_does_not_mutate_input(ml):
    items = [
        _img_msg(0),
        {"type": "function_call_output", "call_id": "c", "output": [_image_part(1)]},
    ]
    originals = deepcopy(items)
    for item in items:
        ml._process_message(item)
    assert items == originals


# --------------------------------------------------------------------------- #
# add_messages
# --------------------------------------------------------------------------- #
def test_add_messages_appends_in_order(ml):
    a, b, c = _msg(0, 3), _msg(1, 3), _msg(2, 3)
    _run(ml.add_messages([a, b]))
    _run(ml.add_messages([c]))
    assert ml.get_messages() == [a, b, c]
    assert [_tag(s) for s in ml.modified_messages] == ["msg00", "msg01", "msg02"]


def test_get_messages_returns_a_copy(ml):
    _run(ml.add_messages([_msg(0, 3)]))
    returned = ml.get_messages()
    returned.append(_msg(1, 3))
    assert ml.get_messages() == [_msg(0, 3)], "mutating the returned list must not change MessageList"


def test_add_messages_collects_files(ml):
    _run(ml.add_messages([_msg(0, 3), _img_msg(1)]))
    _run(ml.add_messages([_img_msg(2)]))
    assert ml.files_modified_messages == [_image_part(1), _image_part(2)]


def test_add_messages_saves_new_messages_to_sql(ml, sql_cls):
    a, b, c = _msg(0, 3), _msg(1, 3), _msg(2, 3)
    _run(ml.add_messages([a, b]))
    _run(ml.add_messages([c]))
    assert _saved_batches(sql_cls) == [[a, b], [c]]


def test_under_token_budget_does_not_summarize(ml, runner):
    _run(ml.add_messages([_msg(i) for i in range(5)]))  # 5 x 13 = 65 <= 70
    assert runner.summarize_calls == []
    assert len(ml.get_messages()) == 5


def test_token_overflow_triggers_one_summarization(ml, runner):
    _run(ml.add_messages([_msg(i) for i in range(6)]))  # 6 x 13 = 78 > 70
    assert len(runner.summarize_calls) == 1


def test_file_overflow_triggers_summarization(make_list, runner):
    ml = make_list(max_tokens=100_000, max_files=4)
    _run(ml.add_messages([_img_msg(i) for i in range(5)]))  # 5 files > 4
    assert len(runner.summarize_calls) == 1


def test_no_resummarization_right_after_summarizing(ml, runner):
    _run(ml.add_messages([_msg(i) for i in range(6)]))  # summarizes; window drops to <= 35 tokens
    _run(ml.add_messages([_msg(9, 2)]))  # +5 tokens: still far below 70
    assert len(runner.summarize_calls) == 1, "token/file counters should be reset after summarizing"


# --------------------------------------------------------------------------- #
# _summarize — token budget
# --------------------------------------------------------------------------- #
@pytest.fixture
def token_summarized(ml, runner):
    """6 messages x 13 tokens with a 70-token budget: keep what fits in 35 -> msg04, msg05."""
    runner.summaries = ["first summary"]
    _run(ml.add_messages([_msg(i) for i in range(6)]))
    return ml


def test_summarization_keeps_newest_within_half_budget(mlm, token_summarized):
    ml = token_summarized
    assert [_tag(m) for m in ml.get_messages()] == ["msg04", "msg05"]
    assert sum(mlm.count(s) for s in ml.modified_messages) <= ml.max_tokens_messages / 2


def test_token_summarization_keeps_lists_in_sync(token_summarized):
    ml = token_summarized
    assert [_tag(s) for s in ml.modified_messages] == [_tag(m) for m in ml.get_messages()]


def test_summarizer_receives_dropped_messages_only(token_summarized, runner):
    text, files = _summarize_input(runner.summarize_calls[0])
    for tag in ("msg00", "msg01", "msg02", "msg03"):
        assert tag in text, f"dropped message {tag} should be summarized"
    for tag in ("msg04", "msg05"):
        assert tag not in text, f"kept message {tag} should not be summarized"
    assert files == []


def test_summary_is_set_from_summarizer(token_summarized):
    assert token_summarized.summary.strip() == "first summary"


def test_next_summary_is_appended_with_separator(token_summarized, runner):
    ml = token_summarized
    runner.summaries = ["second summary"]
    _run(ml.add_messages([_msg(i) for i in range(6, 10)]))  # 26 + 52 = 78 > 70

    assert len(runner.summarize_calls) == 2
    text, _ = _summarize_input(runner.summarize_calls[1])
    assert "first summary" in text, "the old summary should be given as context"

    assert ml.summary.count("first summary") == 1
    assert ml.summary.index("first summary") < ml.summary.index("second summary")
    assert "first summarysecond summary" not in ml.summary, "summaries need a separator"


def test_single_oversized_message_is_kept(make_list):
    ml = make_list(max_tokens=10)  # 7-token budget
    big = _msg(0, 20)  # 23 tokens
    _run(ml.add_messages([big]))
    assert ml.get_messages() == [big]
    assert [_tag(s) for s in ml.modified_messages] == ["msg00"]


def test_nothing_dropped_means_no_summarizer_call(make_list, runner):
    ml = make_list(max_tokens=10)
    _run(ml.add_messages([_msg(0, 20)]))
    assert runner.summarize_calls == [], "no messages left the window, so there is nothing to summarize"


# --------------------------------------------------------------------------- #
# _summarize — file budget
# --------------------------------------------------------------------------- #
@pytest.fixture
def file_summarized(make_list, runner):
    """5 one-image messages with max_files=4: keep what fits in 2 files -> img03, img04."""
    ml = make_list(max_tokens=100_000, max_files=4)
    _run(ml.add_messages([_img_msg(i) for i in range(5)]))
    return ml


def test_file_summarization_keeps_newest_within_half_file_budget(file_summarized):
    ml = file_summarized
    assert [_tag(m) for m in ml.get_messages()] == ["img03", "img04"]
    assert len(ml.files_modified_messages) <= ml.max_files / 2


def test_file_summarization_keeps_lists_in_sync(file_summarized):
    ml = file_summarized
    assert [_tag(s) for s in ml.modified_messages] == [_tag(m) for m in ml.get_messages()]


def test_kept_files_are_in_chronological_order(file_summarized):
    assert file_summarized.files_modified_messages == [_image_part(3), _image_part(4)]


def test_multi_file_message_keeps_file_order_after_summarizing(make_list):
    """Files must stay in placeholder order, also within one message carrying several files."""
    ml = make_list(max_tokens=100_000, max_files=6)  # keep up to 3 files after summarizing
    two_files = {"role": "user", "content": [
        {"type": "input_text", "text": "pair"}, _image_part(10), _image_part(11),
    ]}
    _run(ml.add_messages([_img_msg(0), _img_msg(1), _img_msg(2), _img_msg(3), _img_msg(4), two_files]))
    # 7 files > 6 -> summarize; keep newest within 3 files: img04 (1) + pair (2)
    assert [_tag(m) for m in ml.get_messages()] == ["img04", "pair"]
    assert ml.files_modified_messages == [_image_part(4), _image_part(10), _image_part(11)]


def test_dropped_files_go_to_summarizer(file_summarized, runner):
    text, files = _summarize_input(runner.summarize_calls[0])
    for tag in ("img00", "img01", "img02"):
        assert tag in text
    for tag in ("img03", "img04"):
        assert tag not in text
    assert files == [_image_part(0), _image_part(1), _image_part(2)]


# --------------------------------------------------------------------------- #
# Split + memory upload
# --------------------------------------------------------------------------- #
def test_long_summary_is_split_and_memories_uploaded(make_list, runner):
    memory_client = MagicMock(name="MemoryClient")
    ml = make_list(max_tokens=100, agent_name="Alice", memory_client=memory_client)  # 30-token summary budget
    long_summary = " ".join(["word"] * 40)
    runner.summaries = [long_summary]
    runner.split_result = ("short summary", ["memory one", "memory two"])

    _run(ml.add_messages([_msg(i) for i in range(6)]))

    assert len(runner.split_calls) == 1
    assert long_summary in str(runner.split_calls[0]), "the split agent should get the long summary"
    assert ml.summary == "short summary"

    memory_client.add.assert_called_once()
    chunks, collection = _memory_add_args(memory_client)
    assert chunks == [{"document": "memory one"}, {"document": "memory two"}]
    assert collection == "Alice-recent"


def test_short_summary_is_not_split(make_list, runner):
    memory_client = MagicMock(name="MemoryClient")
    ml = make_list(max_tokens=100, memory_client=memory_client)
    runner.summaries = ["short"]
    _run(ml.add_messages([_msg(i) for i in range(6)]))
    assert runner.split_calls == []
    memory_client.add.assert_not_called()


def test_split_without_memories_uploads_nothing(make_list, runner):
    memory_client = MagicMock(name="MemoryClient")
    ml = make_list(max_tokens=100, memory_client=memory_client)
    runner.summaries = [" ".join(["word"] * 40)]
    runner.split_result = ("short summary", [])
    _run(ml.add_messages([_msg(i) for i in range(6)]))
    assert ml.summary == "short summary"
    memory_client.add.assert_not_called()


# --------------------------------------------------------------------------- #
# Persistence across summarization
# --------------------------------------------------------------------------- #
def test_each_message_saved_exactly_once(ml, sql_cls):
    first = [_msg(i) for i in range(6)]  # triggers a summarization
    second = [_msg(i) for i in range(6, 10)]  # triggers another
    _run(ml.add_messages(first))
    _run(ml.add_messages(second))
    saved = [m for batch in _saved_batches(sql_cls) for m in batch]
    assert saved == first + second
