"""
Copilot CLI transcript parsing.

Confirmed format (from a real session's events.jsonl, shared 2026-08-04,
NOT the earlier "VS Code compatible" assumption, which turned out to be
wrong for the transcript body even though the hook payload envelope fields
matched Claude Code's). Real assistant turns look like:

    {"type": "assistant.message", "data": {"content": "...", "toolRequests": [...], ...}}

Flat "type": "assistant.message" (not "assistant"), content lives directly
under "data" (not nested under "message"), and content is always a plain
string - no content-block-list variant like Claude Code's tool-use-mixed
turns. A single turn can also carry a non-empty content string alongside
populated toolRequests (e.g. "Reading the target file to..."), so every
assistant.message with non-empty content is a candidate - the LAST one
in the file is the final response.

The transcript also contains many other event types (session.start,
hook.start/end, tool.execution_start/complete, permission.requested,
user.message, etc.) - all ignored here.
"""

import json
from pathlib import Path


def extract_last_assistant_message(transcript_path: str) -> str:
    """Returns "" if the file is missing or no assistant.message entry
    with content is found, rather than raising."""
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

            if entry.get("type") != "assistant.message":
                continue

            content = entry.get("data", {}).get("content", "")
            if isinstance(content, str) and content:
                last_text = content

    return last_text
