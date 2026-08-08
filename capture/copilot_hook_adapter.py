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
    """Adapter priority explanation:

    The `priority` attribute determines the order native adapters are
    considered when no telemetry source is configured. `CaptureManager`
    sorts adapters by `priority` (ascending) and calls `is_available()` in
    that order; the first available adapter wins. A lower `priority` value
    is checked earlier and therefore has precedence.

    The numeric value is only used for deterministic ordering/tie-breaking,
    not as a measure of fidelity or correctness. Copilot and Claude Code are
    both Tier 2 captures; their `priority` values simply ensure stable
    behavior if multiple adapters are present simultaneously.
    """

    priority = 6
    adapter_tag = "copilot_hook"
