import pytest
from copy import deepcopy
from unittest.mock import patch, MagicMock
from helpers import *
import sources
from sources import InputSource, InputSourceHub, OutputSource, OutputSourceHub, MessageInputSource, StreamingOutputSource, GradioUI



# TEST INPUT
# messageinput_test_cases = [
    
# ]
# """
# Test cases to test MessageInputSource
# """


inputsourcehub_test_cases = [
    # Both sources have messages initialy and for new_data
    (
        make_messages(7),
        make_messages(3),
        make_messages(8),
        make_messages(2)
    ),
    # Empty initially with messages for new data
    (
        [],
        make_messages(53),
        [],
        make_messages(100)
    ),

    # All empty
    ([], [], [], [])
]
"""
Test cases for input source hub that use MessageInputSource

For each test case, there are 4 arguments in order: 
["initial_inputs1", "new_inputs1", "initial_inputs2", "new_inputs2"]
"""

# TEST INPUT SOURCE HUB
@pytest.mark.parametrize(
        ["initial_inputs1", "new_inputs1", "initial_inputs2", "new_inputs2"],
        inputsourcehub_test_cases
        
)
def test_input_source_hub(initial_inputs1: list[dict], new_inputs1: list[dict], initial_inputs2: list[dict], new_inputs2: list[dict]) -> None:
    """Test the input source hub class with 2 instances of TestInputSource"""

    source1 = MessageInputSource(state=initial_inputs1, new_data=new_inputs1, attention="none")
    source2 = MessageInputSource(state=initial_inputs2, new_data=new_inputs2, attention="none")
    sources = {
        "source1": source1,
        "source2": source2
    }

    hub = InputSourceHub(sources=sources)

    # TEST: has_new should return True since all sources has new_data
    assert hub.has_new() == False, "has_new() returns True although all sources has none attention"

    # TEST: all attentions should be none initialy since the source objects' attentions set to none
    attentions = hub.get_attentions()
    for source, attention in attentions.items():
        assert attention == "none", f"The initial attention of {source} is {attention} when the original sources (before putting in the hub) attentions are set to 'none'. Expected 'none'"


    # TEST: the initial connected statuses should be False
    connected_statuses = hub.get_connected_statuses()
    for source, status in connected_statuses.items():
        assert status == False, f"The connected status of {source} is True before call connect_all. Expected False"


    # TEST: BEFORE CALL connect_all() and the original attentions set to 'none'
    # Test: fetch() should return an empty list
    all_new_data = hub.fetch()
    assert len(all_new_data) == 0, f"fetch() returns a list of {len(all_new_data)} elements when all sources are unconnected and have none attention . Expected an empty list"


    # TEST: change_attentions
    # Test: call change_attention with an invalid value should raise ValueError
    with pytest.raises(ValueError):
        hub.change_attention("source1", "Invalid")

    with pytest.raises(ValueError):
            hub.change_attention("source3", "none")

    # Test: whether change_attentions can actually change attentions
    hub.change_attention("source1", "full")
    hub.change_attention("source2", "simple")
    attentions = hub.get_attentions()
    assert attentions.get("source1") == "full", f"Called change_attentions to set 'source1' to full, got {attentions.get("source1")}. Expected 'full'"
    assert attentions.get("source2") == "simple", f"Called change_attentions to set 'source2' to simple, got {attentions.get("source2")}. Expected 'simple'"

    # TEST: BEFORE CALL connect_all() and the attentions set to full and simple
    # Test: fetch() should return an empty list 
    all_new_data = hub.fetch()
    assert len(all_new_data) == 0, f"fetch() returns a list of {len(all_new_data)} elements when all sources are unconnected and all attentions are not none. Expected an empty list"


    # TEST: call connect_all() should make all sources connected since TestInputSource should always connect successfully
    hub.connect_all()
    connected_statuses = hub.get_connected_statuses()
    for source, status in connected_statuses.items():
        assert status == True, f"The connected status of {source} is False after calling connect_all. Expected True"


    # TEST: AFTER CALL connect_all() AND ATTENTIONS SET TO full and simple
    # Test: has_new() should return True if all sources are connected, have new data and not none attention
    assert hub.has_new() == bool(source1.new_data + source2.new_data), "has_new() should return True when all sources are connected, have new data and not none attention. Expected True" 
    # Test: fetch should return a non-empty list of messages
    expected_list = new_inputs1 + new_inputs2
    actual_list = hub.fetch()
    assert compare_messages(actual_list, expected_list), f"When all sources are connected and have not-none attentions, fetch() return a list with the length {len(actual_list)}. Expected {len(expected_list)}"

    # Test: immediately after fetch(), new fetch() should returns a empty list 
    all_new_data = hub.fetch()
    assert len(all_new_data) == 0, f"When fetch() has just been called, another fetch() call returns a list of {len(all_new_data)} elements. Expected an empty list"

    # Test: immediately after fetch(), states should have the previous new data
    expected_list = initial_inputs1+new_inputs1
    actual_list = source1.state
    assert compare_messages(actual_list, expected_list), f"When fetch() has just been called, source1 state doesn't contain the previous new_data, its length is {len(actual_list)}. Expected length {len(expected_list)}"

    # TEST: has_new should return True when all sources have no new data
    assert hub.has_new() == False, "has_new() returns True although no source has new data"

    # TEST: ATTENTIONS SET TO none and simple
    # Set source1 attention to none
    hub.change_attention("source1", "none")

    # Test: fetch should return a list identical to new_inputs2 after adding new_inputs2 and new_inputs1 to sources
    # Add new_inputs2 and new_inputs1. In pratice, the input sources should add by themselves
    source1.new_data = deepcopy(new_inputs1)
    source2.new_data = deepcopy(new_inputs2)
    expected_list = new_inputs2
    actual_list = hub.fetch()
    assert compare_messages(actual_list, expected_list), f"When all sources are connected and attentions are none and simple, fetch() return a list with the length {len(actual_list)}. Expected {len(expected_list)} (same as new_data in source2)"

    
# TEST OUTPUT
streaming_output_test_cases = [
     (make_phrases(100), make_phrases(14)),
     (make_phrases(0), make_phrases(213)),
     (make_phrases(0), make_phrases(0))
]
@pytest.mark.parametrize(["state", "new_agent_phrases"], streaming_output_test_cases)
def test_streaming_output_source(state: list[str], new_agent_phrases: list[dict]) -> None:
    """
    Test StreamingOutPutSource class

    Inputs:
    state: initial state of the source
    new_agent_phrases: the new phrases to be added 
    """
    source = StreamingOutputSource(in_use=False, state=state)

    # TEST: the initial attributes are as expected
    assert source.state == state, "Initial state wrong"
    assert source.in_use == False, "Initial in_use wrong"
    assert source.connected == False, "Initial connected wrong"
    assert source.new_agent_phrases == [], "Initial connected wrong"

    # TEST: When in_use or connected is false, send_phrase doesn't do anything
    source.in_use = True
    send_phrases(source, new_agent_phrases)
    # Test: when not connected, send should not modify new_agent_phrases
    assert source.new_agent_phrases == [], f"Call send_phrase when not connected. Expected new_agent_phrases not be modified"

    # Test: connect() should make connected True
    source.connect()
    assert source.connected == True, f"connect() fails to make connected True"

    # Test: when not in use, send should not modify new_agent_phrases
    source.in_use=False
    send_phrases(source, new_agent_phrases)
    assert source.new_agent_phrases == [], f"Call send_phrase when not in use. Expected new_agent_phrases not be modified"

    # TEST: WHen in use and connected, send_phrase should add new phrases to new_agent_phrases
    source.in_use = True
    send_phrases(source, new_agent_phrases)
    assert source.new_agent_phrases == new_agent_phrases, f"Call send_phrase when in use and connected. Expected new_agent_phrases to be modified"

    # TEST: fetch() consume new_agent_phrases and extend state
    returned_phrases = source.fetch()
    assert returned_phrases == new_agent_phrases, "fetch() doesn't return correct phrases"
    assert source.new_agent_phrases == [], "send_phrase() doesn't empty new_agent_phrases"
    assert sorted(source.state) == sorted(state + new_agent_phrases), "send_phrase() doesn't append the new phrase to state"


# ---------------------------------------------------------------------------
# TEST MessageInputSource
# ---------------------------------------------------------------------------
# NOTE: Some assertions below intentionally pin the *current* behaviour of the
# code (see REPORT.md, items #1 and #2). Where that behaviour is suspect it is
# flagged with a comment referencing the report so the test stays green against
# the code as-is while still documenting the concern.

def _msg(i: int) -> dict:
    """A single ResponseAPI-style message dict."""
    return {"role": "user", "content": f"message {i}"}


def test_message_input_source_init_defaults():
    """A freshly constructed source starts empty, disconnected, and full attention."""
    source = MessageInputSource()
    assert source.state == [], "Initial state should be an empty list"
    assert source.new_data == [], "Initial new_data should be an empty list"
    assert source.connected is False, "A new source should not be connected"
    assert source.attention == "full", "Default attention should be 'full'"


def test_message_input_source_instances_are_independent():
    """The mutable default args must not be shared between instances (defused by deepcopy)."""
    a = MessageInputSource()
    b = MessageInputSource()
    assert a.state is not b.state, "Two instances share the same state list"
    assert a.new_data is not b.new_data, "Two instances share the same new_data list"
    a.state.append(_msg(0))
    a.new_data.append(_msg(1))
    assert b.state == [], "Mutating one instance's state leaked into another"
    assert b.new_data == [], "Mutating one instance's new_data leaked into another"


def test_message_input_source_init_deepcopies_inputs():
    """Constructor should deepcopy state/new_data so later edits to the originals don't leak in."""
    initial_state = [_msg(0)]
    initial_new = [_msg(1)]
    source = MessageInputSource(state=initial_state, new_data=initial_new, attention="full")

    initial_state.append(_msg(99))
    initial_new.append(_msg(98))
    initial_new[0]["content"] = "mutated"

    assert source.state == [{"role": "user", "content": "message 0"}], "state was not deepcopied"
    assert source.new_data == [{"role": "user", "content": "message 1"}], "new_data was not deepcopied"


def test_message_input_source_invalid_attention_raises():
    """An invalid attention value must raise ValueError at construction."""
    with pytest.raises(ValueError):
        MessageInputSource(attention="loud")


@pytest.mark.parametrize("attention", ["full", "simple", "none"])
def test_message_input_source_valid_attention_accepted(attention):
    """All three documented attention values are accepted."""
    source = MessageInputSource(attention=attention)
    assert source.attention == attention


def test_message_input_source_attention_setter_validates():
    """The attention setter rejects invalid values and accepts valid ones."""
    source = MessageInputSource()
    with pytest.raises(ValueError):
        source.attention = "invalid"
    source.attention = "none"
    assert source.attention == "none"


def test_message_input_source_connect():
    """connect() flips the connected flag to True."""
    source = MessageInputSource()
    assert source.connected is False
    source.connect()
    assert source.connected is True


def test_message_input_source_add_data_noop_when_disconnected():
    """add_data does nothing while the source is not connected."""
    source = MessageInputSource(attention="full")
    source.add_data([_msg(1)])
    assert source.new_data == [], "add_data should be a no-op when disconnected"


def test_message_input_source_add_data_noop_when_attention_none():
    """add_data does nothing when attention is 'none', even if connected."""
    source = MessageInputSource(attention="none")
    source.connect()
    source.add_data([_msg(1)])
    assert source.new_data == [], "add_data should be a no-op when attention is 'none'"


def test_message_input_source_add_data_appends_and_deepcopies():
    """When connected and attentive, add_data appends a deepcopy of the data."""
    source = MessageInputSource(attention="full")
    source.connect()
    payload = [_msg(1), _msg(2)]
    source.add_data(payload)
    assert source.new_data == [{"role": "user", "content": "message 1"},
                               {"role": "user", "content": "message 2"}]
    # Mutating the original payload must not affect stored data (deepcopy).
    payload[0]["content"] = "mutated"
    payload.append(_msg(3))
    assert source.new_data == [{"role": "user", "content": "message 1"},
                               {"role": "user", "content": "message 2"}]


@pytest.mark.parametrize("attention,expected", [
    ("full", True),
    ("simple", True),
    ("none", False),
])
def test_message_input_source_has_new(attention, expected):
    """When connected, has_new() is True only when there is new_data AND attention != 'none'."""
    source = MessageInputSource(new_data=[_msg(1)], attention=attention)
    source.connect()
    assert source.has_new() is expected


def test_message_input_source_has_new_false_when_empty():
    """has_new() is False when there is no new_data, regardless of attention."""
    source = MessageInputSource(attention="full")
    source.connect()
    assert source.has_new() is False


def test_message_input_source_has_new_false_when_disconnected():
    """has_new() requires connection (see REPORT.md #2): a disconnected source reports False."""
    source = MessageInputSource(new_data=[_msg(1)], attention="full")
    assert source.connected is False
    assert source.has_new() is False, "has_new() must be False while disconnected"
    source.connect()
    assert source.has_new() is True, "has_new() should be True once connected with pending data"


@pytest.mark.parametrize("attention", ["full", "simple"])
def test_message_input_source_fetch_returns_and_consumes_when_connected(attention):
    """When connected and attentive, fetch() returns the new_data and moves it into state."""
    data = [_msg(1), _msg(2)]
    source = MessageInputSource(new_data=deepcopy(data), attention=attention)
    source.connect()

    returned = source.fetch()
    assert returned == data, "fetch() should return the pending new_data"
    assert source.new_data == [], "fetch() should clear new_data"
    assert source.state == data, "fetch() should move new_data into state"

    # A second fetch with nothing pending returns an empty list.
    assert source.fetch() == [], "fetch() with no pending data should return []"


def test_message_input_source_fetch_none_attention_returns_empty_and_preserves_data():
    """
    With attention 'none', fetch() returns [] and does NOT consume new_data
    (guard checked before draining — see REPORT.md #1, now fixed).
    """
    data = [_msg(1)]
    source = MessageInputSource(new_data=deepcopy(data), attention="none")
    source.connect()

    assert source.fetch() == [], "none attention should return []"
    assert source.new_data == data, "new_data must be preserved when attention is 'none'"
    assert source.state == [], "nothing should be drained into state"


def test_message_input_source_fetch_disconnected_returns_empty_and_preserves_data():
    """
    While disconnected, fetch() returns [] and does NOT consume new_data, so the
    pending input survives until the source is connected (see REPORT.md #1, now fixed).
    """
    data = [_msg(1)]
    source = MessageInputSource(new_data=deepcopy(data), attention="full")
    assert source.connected is False

    assert source.fetch() == [], "disconnected fetch should return []"
    assert source.new_data == data, "new_data must be preserved while disconnected"
    assert source.state == [], "nothing should be drained into state"

    # Once connected, the previously-pending data is delivered normally.
    source.connect()
    assert source.fetch() == data, "connecting then fetching should deliver the preserved data"
    assert source.new_data == []


# ---------------------------------------------------------------------------
# TEST OutputSourceHub
# ---------------------------------------------------------------------------

class RecordingOutputSource(OutputSource):
    """A minimal OutputSource used to observe exactly what the hub forwards."""

    def __init__(self, in_use: bool = True):
        super().__init__(in_use=in_use)
        self.received_messages: list = []
        self.received_phrases: list = []

    def send_messages(self, messages: list[dict]) -> None:
        self.received_messages.append(messages)

    def send_phrase(self, phrase: str) -> None:
        self.received_phrases.append(phrase)

    def fetch(self) -> list:
        return []


def test_output_source_hub_init_copies_sources_dict():
    """The hub stores a copy of the sources dict, not the caller's dict."""
    src = RecordingOutputSource()
    original = {"a": src}
    hub = OutputSourceHub(sources=original)
    original["b"] = RecordingOutputSource()
    assert "b" not in hub.sources, "Hub should hold its own copy of the sources dict"
    assert hub.sources["a"] is src, "Hub should keep the same source object references"


def test_output_source_hub_connect_all():
    """connect_all() connects every registered source."""
    s1, s2 = RecordingOutputSource(), RecordingOutputSource()
    hub = OutputSourceHub(sources={"s1": s1, "s2": s2})
    assert s1.connected is False and s2.connected is False
    hub.connect_all()
    assert s1.connected is True and s2.connected is True


def test_output_source_hub_send_messages_respects_in_use():
    """send_messages only reaches sources whose in_use flag is True."""
    on = RecordingOutputSource(in_use=True)
    off = RecordingOutputSource(in_use=False)
    hub = OutputSourceHub(sources={"on": on, "off": off})
    hub.connect_all()

    messages = [{"role": "assistant", "content": "hi"}]
    hub.send_messages(messages)

    assert on.received_messages == [messages], "in_use source should receive the messages"
    assert off.received_messages == [], "not-in_use source should receive nothing"


def test_output_source_hub_send_messages_deepcopies():
    """The hub deepcopies messages so later mutation of the original does not leak through."""
    sink = RecordingOutputSource(in_use=True)
    hub = OutputSourceHub(sources={"sink": sink})
    hub.connect_all()

    messages = [{"role": "assistant", "content": "original"}]
    hub.send_messages(messages)
    messages[0]["content"] = "mutated"

    assert sink.received_messages[0] == [{"role": "assistant", "content": "original"}], \
        "hub should have forwarded a deepcopy, not a live reference"


def test_output_source_hub_send_phrase_respects_in_use():
    """send_phrase only reaches in_use sources."""
    on = RecordingOutputSource(in_use=True)
    off = RecordingOutputSource(in_use=False)
    hub = OutputSourceHub(sources={"on": on, "off": off})
    hub.connect_all()

    hub.send_phrase("token")
    assert on.received_phrases == ["token"], "in_use source should receive the phrase"
    assert off.received_phrases == [], "not-in_use source should receive nothing"


def test_output_source_hub_change_in_use():
    """change_in_use toggles a source's in_use flag and gates delivery accordingly."""
    sink = RecordingOutputSource(in_use=False)
    hub = OutputSourceHub(sources={"sink": sink})
    hub.connect_all()

    hub.send_phrase("first")
    assert sink.received_phrases == [], "phrase should not reach a not-in_use source"

    hub.change_in_use("sink", True)
    assert sink.in_use is True
    hub.send_phrase("second")
    assert sink.received_phrases == ["second"], "phrase should reach it once in_use is True"


def test_output_source_hub_change_in_use_unknown_raises():
    """change_in_use raises ValueError for an unknown source name."""
    hub = OutputSourceHub(sources={"sink": RecordingOutputSource()})
    with pytest.raises(ValueError):
        hub.change_in_use("nope", True)


def test_output_source_hub_integration_with_streaming_source():
    """End-to-end: a StreamingOutputSource wired into the hub streams then fetches back."""
    stream = StreamingOutputSource(in_use=True)
    hub = OutputSourceHub(sources={"stream": stream})

    # Before connect_all(): StreamingOutputSource.send_phrase requires connected, so nothing lands.
    hub.send_phrase("dropped")
    assert stream.new_agent_phrases == [], "phrase should be dropped while source is disconnected"

    hub.connect_all()
    hub.send_phrase("hello")
    hub.send_phrase("||END_OF_RESPONSE||")
    assert stream.fetch() == ["hello", "||END_OF_RESPONSE||"], \
        "connected in_use source should collect and return streamed phrases"


# ---------------------------------------------------------------------------
# TEST GradioUI
# ---------------------------------------------------------------------------
# GradioUI.__init__ calls asyncio.gather(self.start()), which both requires a
# running event loop and launches a real Gradio server (see REPORT.md #4). The
# helpers below patch that out so the class can be exercised in a unit test.

def _make_bare_gradio_ui():
    """Construct a GradioUI without running start() or touching the event loop."""
    # Use a plain (non-async) MagicMock for start so calling self.start() returns a
    # value rather than an un-awaited coroutine (patching an async def would create
    # an AsyncMock and leak a "coroutine was never awaited" warning).
    mock_start = MagicMock(return_value=None)
    mock_gather = MagicMock(return_value=None)
    with patch.object(sources.GradioUI, "start", mock_start), \
         patch.object(sources.asyncio, "gather", mock_gather):
        ui = GradioUI()
    return ui, mock_start, mock_gather


def _run_start_coroutine(coro):
    """Drive a no-await coroutine to completion synchronously (used for asyncio.gather patch)."""
    try:
        coro.send(None)
    except StopIteration:
        pass
    return None


def _make_gradio_ui_capturing_callbacks():
    """
    Construct a GradioUI with the `gradio` module and event loop mocked out, and
    capture the inner `fetch` / `send_user_message` callbacks that start() registers.
    """
    fake_gr = MagicMock()
    captured: dict = {}

    def capture_tick(*args, **kwargs):
        captured["fetch"] = kwargs.get("fn", args[0] if args else None)

    def capture_click(*args, **kwargs):
        captured["send_user_message"] = args[0] if args else kwargs.get("fn")

    fake_gr.Timer.return_value.tick.side_effect = capture_tick
    fake_gr.Button.return_value.click.side_effect = capture_click

    with patch.object(sources, "gr", fake_gr), \
         patch.object(sources.asyncio, "gather", side_effect=_run_start_coroutine):
        ui = GradioUI()

    return ui, captured["fetch"], captured["send_user_message"]


def test_gradio_ui_init_wiring():
    """Construction wires up the expected attributes and kicks off start() via gather."""
    ui, mock_start, mock_gather = _make_bare_gradio_ui()

    assert ui.messages == [], "messages should start empty"
    assert isinstance(ui.input_source, MessageInputSource), "input_source should be a MessageInputSource"
    assert isinstance(ui.output_source, StreamingOutputSource), "output_source should be a StreamingOutputSource"
    assert mock_start.called, "__init__ should invoke start()"
    assert mock_gather.called, "__init__ should schedule start() via asyncio.gather"


def test_gradio_ui_connects_its_sources():
    """GradioUI connects both of its sources in __init__ (see REPORT.md #5, now fixed)."""
    ui, _, _ = _make_bare_gradio_ui()
    assert ui.input_source.connected is True, "GradioUI should connect its input source"
    assert ui.output_source.connected is True, "GradioUI should connect its output source"


def test_gradio_ui_instances_are_independent():
    """Each GradioUI gets its own message list and source objects (no shared mutable state)."""
    ui1, _, _ = _make_bare_gradio_ui()
    ui2, _, _ = _make_bare_gradio_ui()

    assert ui1.messages is not ui2.messages
    assert ui1.input_source is not ui2.input_source
    assert ui1.output_source is not ui2.output_source

    ui1.messages.append({"role": "user", "content": "x"})
    assert ui2.messages == [], "one UI's messages leaked into another"


def test_gradio_ui_send_user_message_appends_and_pops_empty_assistant():
    """send_user_message drops a trailing empty assistant turn, then appends the user message."""
    ui, _fetch, send_user_message = _make_gradio_ui_capturing_callbacks()
    # Simulate the empty assistant placeholder that fetch() leaves after a response.
    ui.messages.append({"role": "assistant", "content": ""})

    cleared, messages = send_user_message("hello there")

    assert cleared == "", "the textbox value should be cleared"
    assert messages == [{"role": "user", "content": "hello there"}], \
        "empty assistant placeholder should be replaced by the new user message"
    # The input source is connected (REPORT.md #5 fix), so the message also reaches it.
    assert ui.input_source.new_data == [{"role": "user", "content": "hello there"}], \
        "the typed message should be forwarded to the (now connected) input source"


def test_gradio_ui_fetch_reassembles_streamed_response():
    """fetch() concatenates streamed token deltas and closes the turn on the sentinel."""
    ui, fetch, _send = _make_gradio_ui_capturing_callbacks()

    # output_source is already connected by GradioUI.__init__ (REPORT.md #5 fix).
    ui.output_source.send_phrase("Hello")
    ui.output_source.send_phrase(" world")
    ui.output_source.send_phrase("||END_OF_RESPONSE||")

    messages = fetch()
    assert messages == [
        {"role": "assistant", "content": "Hello world"},
        {"role": "assistant", "content": ""},
    ], "streamed deltas should join into one assistant message, then a fresh empty turn"


def test_gradio_ui_fetch_joins_leftover_tokens_without_spaces():
    """
    Streamed token deltas that arrive without a sentinel in the batch are concatenated
    with '' (no spurious spaces) — REPORT.md #7, now fixed.
    """
    ui, fetch, _send = _make_gradio_ui_capturing_callbacks()
    ui.messages.append({"role": "user", "content": "hi"})

    for tok in ["A", "B", "C"]:
        ui.output_source.send_phrase(tok)

    messages = fetch()
    assert messages[-1]["content"] == "ABC", \
        "leftover token deltas should join with '' (no inserted spaces)"










    


