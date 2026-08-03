"""
Claude Code hook adapter - Tier 2. See docs/finding-lm-api-tier1.md for why
this exists (Tier 1 isn't viable for closed agents) and hook_shared.py /
hook_adapter_base.py for the mechanics.

Fixed in this revision: earlier version globbed *__*.json in
pending_captures/ with no adapter-tag prefix, meaning if a second agent
(Copilot) ever wrote into the same directory, this adapter would happily
pick up Copilot's captures and mislabel them as Claude Code's. Now inherits
FileBridgedHookAdapter, which scopes the glob to this adapter's own tag.
"""

from .hook_adapter_base import FileBridgedHookAdapter


class ClaudeCodeHookAdapter(FileBridgedHookAdapter):
    """priority = 5: below a hypothetical fully-real LmApiAdapter (0, still
    fake/narrowed-scope per the Tier 1 finding), above DebugAdapter (10,
    still fake) and GitAdapter (100, last resort)."""

    priority = 5
    adapter_tag = "claude_code_hook"
