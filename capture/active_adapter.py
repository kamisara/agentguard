"""
Optional single-active-adapter gate.

Problem this solves: GitHub Copilot CLI reads .claude/settings.json as a
documented cross-tool compatibility source. If both .claude/settings.json
and .github/hooks/*.json are registered at the same time, a single Copilot
session fires BOTH hook handlers - one produces a real capture, the other
(Claude Code's handler, which doesn't understand Copilot's transcript
format) produces an empty one. Claude Code does not read .github/hooks/*.json,
so this asymmetry only bites when Copilot is the one actually running.

Rather than editing settings.json every time you switch which agent you're
testing, set which adapter is "active" once via a marker file. Both hook
handlers check this before writing anything - if a different adapter is
marked active, they no-op instead of producing a stray/empty capture.

Absence of the marker file means "no restriction" - all handlers fire
normally. This is deliberate: the two-agent isolation test
(test_copilot_hook.py) relies on both firing at once, and clears any
marker as part of its .agentguard cleanup.
"""

from pathlib import Path
from typing import Optional


def _marker_path(cwd: str) -> Path:
    return Path(cwd) / ".agentguard" / "active_adapter.txt"


def get_active_adapter(cwd: str) -> Optional[str]:
    """Returns the active adapter tag, or None if unrestricted (all
    handlers fire)."""
    path = _marker_path(cwd)
    if not path.exists():
        return None
    value = path.read_text().strip()
    return value or None


def set_active_adapter(cwd: str, adapter_tag: Optional[str]) -> None:
    """Set which adapter should be the only one to fire. Pass None to
    clear the restriction (all handlers fire again)."""
    path = _marker_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    if adapter_tag is None:
        if path.exists():
            path.unlink()
    else:
        path.write_text(adapter_tag)


def is_adapter_active(cwd: str, adapter_tag: str) -> bool:
    """True if this adapter should proceed - either no restriction is set,
    or the restriction matches this adapter exactly."""
    active = get_active_adapter(cwd)
    return active is None or active == adapter_tag
