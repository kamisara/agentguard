"""
Shared logic for file-bridged hook handlers.

Claude Code and GitHub Copilot's "VS Code compatible" hook payload format
use identical field names for the hook ENVELOPE (session_id, transcript_path,
cwd, hook_event_name, prompt) - confirmed against both products' docs, not
assumed. That's why the stash/pair mechanism below is shared rather than
duplicated per agent.

The transcript BODY format is NOT shared - confirmed different via a real
Copilot session (2026-08-04). See claude_code_hooks/transcript_parser.py
and copilot_hooks/transcript_parser.py, and
docs/finding-copilot-transcript-format.md for what happened when that was
wrongly assumed to be identical.

AUTOMATIC agent detection (no developer/config action required): Copilot
CLI reads .claude/settings.json as a documented cross-tool source, so a
single Copilot session can fire BOTH hook handlers at once. Since this
product ships as something that runs unattended (a VS Code extension, a
background process) - not something a developer manually configures per
session - detection has to happen without any human declaring which agent
is "active." At UserPromptSubmit time there's no transcript yet, so both
handlers harmlessly stash a prompt (internal, not user-facing). At Stop
time, a real transcript exists, and each handler's schema_matcher checks
whether it actually looks like ITS OWN agent's format before writing
anything. If it doesn't, that handler cleans up its stash and produces
NO output - automatically, every time, no manual step.

active_adapter.py still exists as an optional manual override (useful for
testing, or forcing a choice), but is no longer required for correct
behavior - see set_active_adapter.py.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .active_adapter import is_adapter_active


def _pending_dir(cwd: str) -> Path:
    d = Path(cwd) / ".agentguard" / "pending_captures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prompt_stash_path(cwd: str, adapter_tag: str, session_id: str) -> Path:
    # adapter_tag prefixed so two different agents' hooks writing into the
    # same pending_captures/ directory never collide or get picked up by
    # the wrong adapter - see hook_adapter_base.py for the read side of this.
    return _pending_dir(cwd) / f"{adapter_tag}__{session_id}__prompt.json"


def handle_user_prompt_submit(payload: dict, adapter_tag: str) -> None:
    """No schema check possible here - there's no transcript yet at this
    point in the session. If a manual override is set via
    active_adapter.py, it's honored; otherwise this always stashes. That's
    fine: the stash is an internal intermediate file, never shown to the
    user, and gets cleaned up automatically at Stop time by whichever
    handler's schema_matcher determines the session wasn't actually theirs.
    """
    if not is_adapter_active(payload["cwd"], adapter_tag):
        return  # manual override says a different adapter is active

    session_id = payload["session_id"]
    stash_path = _prompt_stash_path(payload["cwd"], adapter_tag, session_id)
    stash_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "prompt": payload.get("prompt", ""),
                "cwd": payload["cwd"],
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )


def handle_stop(
    payload: dict,
    adapter_tag: str,
    transcript_parser: Callable[[str], str],
    schema_matcher: Callable[[str], bool],
) -> None:
    """transcript_parser extracts the final assistant response text.
    schema_matcher automatically confirms the transcript actually looks
    like THIS agent's format before anything gets written - this is the
    real fix for cross-tool config firing, requiring zero developer action.

    Confirmed (not assumed) that Claude Code and Copilot use genuinely
    different transcript schemas:
      - Claude Code: {"type": "assistant", "message": {"content": ...}}
      - Copilot:     {"type": "assistant.message", "data": {"content": ...}}

    Each agent's hook_handler.py passes its own parser + matcher pair
    (claude_code_hooks/transcript_parser.py or
    copilot_hooks/transcript_parser.py) - only the stash/pair mechanism
    below is genuinely shared.
    """
    session_id = payload["session_id"]
    cwd = payload["cwd"]

    if not is_adapter_active(cwd, adapter_tag):
        return  # manual override says a different adapter is active

    stash_path = _prompt_stash_path(cwd, adapter_tag, session_id)
    if not stash_path.exists():
        # No matching UserPromptSubmit was captured for this session/agent -
        # nothing to pair the response with, so skip rather than emit a
        # half-event.
        return

    transcript_path = payload.get("transcript_path", "")

    if not schema_matcher(transcript_path):
        # AUTOMATIC detection: this transcript doesn't look like it came
        # from our agent at all. In practice this is the cross-tool
        # config case - Copilot firing Claude Code's handler (or vice
        # versa) for a session that isn't actually Claude Code's. Clean
        # up the stash so it doesn't linger, but write nothing - no
        # developer action was needed to reach this conclusion.
        stash_path.unlink()
        return

    stashed = json.loads(stash_path.read_text())
    response_text = transcript_parser(transcript_path)

    completed = {
        "adapter": adapter_tag,
        "session_id": session_id,
        "prompt": stashed["prompt"],
        "response": response_text,
        "cwd": cwd,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = _pending_dir(cwd) / f"{adapter_tag}__{session_id}__{uuid.uuid4()}.json"
    out_path.write_text(json.dumps(completed))

    stash_path.unlink()
