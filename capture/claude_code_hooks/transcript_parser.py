"""
Claude Code transcript parsing.

Confirmed format (via real testing in a prior session, not the assumption
that shipped originally): one JSON object per line,
{"type": "assistant", "message": {"content": ...}} for assistant turns.
content is either a plain string, or a list of content blocks
(e.g. tool_use + text mixed) when the turn included tool calls alongside
text.
"""

import json
from pathlib import Path


def extract_last_assistant_message(transcript_path: str) -> str:
    """Returns "" if the file is missing or no assistant turn is found,
    rather than raising - a missing/malformed transcript shouldn't crash
    the hook and block the developer's session."""
    path = Path(transcript_path)
    if not path.exists():
        return ""

    last_text = ""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "assistant":
                continue

            message = entry.get("message", {})
            content = message.get("content", "")

            if isinstance(content, str):
                if content:
                    last_text = content
            elif isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                if text_parts:
                    last_text = "\n".join(text_parts)

    return last_text


def transcript_looks_like_claude_code(transcript_path: str) -> bool:
    """Automatic agent detection - no developer/config action needed.

    Scans for at least one entry shaped like Claude Code's assistant turn
    ({"type": "assistant", "message": {...}}). If a transcript has ZERO
    such entries, it almost certainly wasn't produced by Claude Code - the
    real, observed case is Copilot CLI reading .claude/settings.json as a
    cross-tool source and firing this handler for its OWN session, whose
    transcript is entirely "assistant.message"-shaped instead.

    NOTE: Claude Code's real transcript format has never been verified
    live in this project (that test was deferred). This check reuses the
    same "type": "assistant" assumption extract_last_assistant_message()
    is built on - if that assumption is later found wrong (the way the
    Copilot one was), this function needs the same correction.
    """
    path = Path(transcript_path)
    if not path.exists():
        return False

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "assistant" and "message" in entry:
                return True

    return False
