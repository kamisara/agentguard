"""
GitHub Copilot hook adapter - Tier 2, same mechanism as Claude Code's.

Copilot's hooks reference documents a "VS Code compatible" payload format,
selected by registering hooks with PascalCase event names (UserPromptSubmit,
Stop) instead of camelCase (userPromptSubmitted, agentStop). In that format,
the field names are identical to Claude Code's: session_id, transcript_path,
cwd, hook_event_name, prompt. That's confirmed from Copilot's own hooks
reference, not assumed - it's a deliberate interop format, not a
coincidence.

NOT YET VERIFIED: whether Copilot's actual transcript file (pointed to by
transcript_path) uses the same JSONL "type": "assistant" schema as Claude
Code's. hook_shared._extract_last_assistant_message assumes so. If a real
Copilot session's transcript differs, that's the one function that needs
adjusting - everything else in this file is unaffected.
"""

from .hook_adapter_base import FileBridgedHookAdapter


class CopilotHookAdapter(FileBridgedHookAdapter):
    """priority = 6: not ranked above or below ClaudeCodeHookAdapter (5) for
    any fidelity reason - both are equally real Tier 2 captures. The
    numbers only need to be distinct so CaptureManager's sort is
    deterministic; if both were somehow available at once, ClaudeCodeHookAdapter
    would win arbitrarily. In practice only one agent is active in a given
    session, so this tie-break rarely matters."""

    priority = 6
    adapter_tag = "copilot_hook"
