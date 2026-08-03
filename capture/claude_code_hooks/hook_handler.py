"""
The actual script Claude Code invokes via .claude/settings.json.

Thin wrapper around capture/hook_shared.py - see that module for the real
logic and the transcript-format assumption that applies to both this and
copilot_hooks/hook_handler.py.
"""

import json
import sys
from pathlib import Path

# Allow running this script directly (as Claude Code will) without the
# project root already being on sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from capture.hook_shared import handle_user_prompt_submit, handle_stop

ADAPTER_TAG = "claude_code_hook"


def main() -> None:
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")

    if event == "UserPromptSubmit":
        handle_user_prompt_submit(payload, ADAPTER_TAG)
    elif event == "Stop":
        handle_stop(payload, ADAPTER_TAG)
    # Silently ignore any other event - this script should only be
    # registered against these two, but being defensive costs nothing.


if __name__ == "__main__":
    main()

