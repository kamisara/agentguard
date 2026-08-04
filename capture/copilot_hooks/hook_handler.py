"""
The actual script GitHub Copilot invokes via .github/hooks/*.json,
configured with PascalCase event names to select the "VS Code compatible"
payload format for the hook envelope (session_id, cwd, transcript_path
fields match Claude Code's - confirmed from Copilot's own hooks reference).

IMPORTANT: the payload ENVELOPE matching Claude Code does NOT mean the
TRANSCRIPT format matches - it doesn't, confirmed via a real session on
2026-08-04. See transcript_parser.py, built from real events.jsonl output,
not the earlier same-as-Claude-Code assumption.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from capture.hook_shared import handle_user_prompt_submit, handle_stop
from capture.copilot_hooks.transcript_parser import extract_last_assistant_message

ADAPTER_TAG = "copilot_hook"


def main() -> None:
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")

    if event == "UserPromptSubmit":
        handle_user_prompt_submit(payload, ADAPTER_TAG)
    elif event == "Stop":
        handle_stop(payload, ADAPTER_TAG, extract_last_assistant_message)


if __name__ == "__main__":
    main()
