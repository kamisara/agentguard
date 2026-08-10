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

from ..types import ToolCall


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


def extract_tool_calls(transcript_path: str) -> list:
    """Sprint 3, Day 2. CONFIRMED real shape (live session, 2026-08-04 -
    the same transcript that fed the debugging for the transcript-format
    finding). Tool calls appear across two event types:

      - "assistant.message" events carry data.toolRequests, a list of
        {"toolCallId": ..., "name": ..., "arguments": {...}}
      - "tool.execution_complete" events carry data.toolCallId and
        data.result (the actual output), matched by toolCallId to the
        request above

    This is real confirmed field naming, not inferred from documentation -
    pulled directly from an actual events.jsonl excerpt shared during live
    debugging."""
    path = Path(transcript_path)
    if not path.exists():
        return []

    calls_by_id = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = entry.get("type")
            data = entry.get("data", {})

            if etype == "assistant.message":
                for req in data.get("toolRequests") or []:
                    call_id = req.get("toolCallId")
                    if not call_id:
                        continue
                    c = calls_by_id.setdefault(call_id, {})
                    c["name"] = req.get("name", "unknown")
                    c["args"] = req.get("arguments") or {}
            elif etype == "tool.execution_complete":
                call_id = data.get("toolCallId")
                if not call_id:
                    continue
                c = calls_by_id.setdefault(call_id, {})
                result = data.get("result")
                if isinstance(result, (dict, list)):
                    c["output"] = json.dumps(result)
                elif result is not None:
                    c["output"] = str(result)

    return [
        ToolCall(name=c.get("name", "unknown"), args=c.get("args", {}), output=c.get("output"))
        for c in calls_by_id.values()
    ]


def transcript_looks_like_copilot(transcript_path: str) -> bool:
    """Automatic agent detection - no developer/config action needed.

    Scans for at least one entry shaped like Copilot's assistant turn
    ({"type": "assistant.message", "data": {...}}). If zero such entries
    exist, this transcript almost certainly wasn't produced by Copilot -
    this is the automatic replacement for manually toggling which agent
    is "active": each hook handler checks the transcript it's actually
    been handed, rather than the developer having to declare it upfront.

    This one IS built on a confirmed-real format (2026-08-04 live session),
    unlike the equivalent Claude Code check, which still rests on an
    unverified assumption.
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
            if entry.get("type") == "assistant.message" and "data" in entry:
                return True

    return False
