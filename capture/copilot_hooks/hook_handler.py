"""
The actual script GitHub Copilot invokes via .github/hooks/*.json,
configured with PascalCase event names to select the "VS Code compatible"
payload format - see copilot_hook_adapter.py for why that format was
chosen (its field names match Claude Code's exactly, confirmed against
Copilot's own hooks reference).

Thin wrapper around capture/hook_shared.py, same as
claude_code_hooks/hook_handler.py - only ADAPTER_TAG differs.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from capture.hook_shared import handle_user_prompt_submit, handle_stop

ADAPTER_TAG = "copilot_hook"


def main() -> None:
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")

    if event == "UserPromptSubmit":
        handle_user_prompt_submit(payload, ADAPTER_TAG)
    elif event == "Stop":
        handle_stop(payload, ADAPTER_TAG)


if __name__ == "__main__":
    main()
