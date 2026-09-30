"""
Contain helper function for testing
"""
from sources import StreamingOutputSource

def make_messages(n: int) -> list[dict]:
    """Generate a list of n dump messages for testing"""

    def make_message(i):
        role = "user" if i % 2 == 0 else "assistant"
        part_type = "input_text" if role == "user" else "output_text"
        return {
            "role": role,
            "content": [{"type": part_type, "text": f"message {i}"}] if i % 3 == 0 else f"message {i}",
        }

    return [[make_message(j) for j in range(i)] for i in range(n)]

def compare_messages(a, b):
    """Compare 2 lists of dicts. (used for comparing 2 list of messages)"""
    if len(a) != len(b):
        return False
    unmatched = list(b)
    for item in a:
        if item in unmatched:
            unmatched.remove(item)
        else:
            return False
    return True


def make_phrases(n: int) -> list[str]:
    """Generate a list of n dump phrases for testing"""
    return ["string" for _ in range(n)]

def send_phrases(source: StreamingOutputSource, phrases: list[dict]) -> None:
    "Send a list of phrases to a StreamingOutputSource"
    for phrase in phrases:
        source.send_phrase(phrase)