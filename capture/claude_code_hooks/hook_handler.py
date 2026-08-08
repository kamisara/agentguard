"""
The actual script Claude Code invokes via .claude/settings.json.

Thin wrapper around capture/hook_shared.py (stash/pair mechanism, shared
across agents) and transcript_parser.py (Claude Code specific - transcript
formats are NOT shared between agents, confirmed via real Copilot testing).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from capture.hook_shared import handle_user_prompt_submit, handle_stop
from capture.claude_code_hooks.transcript_parser import (
    extract_last_assistant_message,
    transcript_looks_like_claude_code,
)

ADAPTER_TAG = "claude_code_hook"


def main() -> None:
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")

    if event == "UserPromptSubmit":
        handle_user_prompt_submit(payload, ADAPTER_TAG)
    elif event == "Stop":
        handle_stop(
            payload,
            ADAPTER_TAG,
            extract_last_assistant_message,
            transcript_looks_like_claude_code,
        )
    # Silently ignore any other event - this script should only be
    # registered against these two, but being defensive costs nothing.


if __name__ == "__main__":
    main()

