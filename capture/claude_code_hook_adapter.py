"""
Claude Code hook adapter - Tier 2, the actual primary path for real-time
capture against a closed agent (see docs/finding-lm-api-tier1.md for why
Tier 1 doesn't work and this took its place as priority=5).

This adapter does NOT talk to Claude Code directly. It has no way to - a
BaseAdapter is pull-based, but Claude Code's hooks are push-based (it calls
hook_handler.py, not the other way around). The bridge between the two is
the filesystem: hook_handler.py writes completed captures to
.agentguard/pending_captures/, and this adapter reads them.

is_available() and capture() are therefore both filesystem checks, not API
calls - genuinely different in character from a hypothetical direct
integration, but this is what a push-based external process requires.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .interfaces import BaseAdapter
from .types import CaptureEvent


class ClaudeCodeHookAdapter(BaseAdapter):
    """priority = 5: below a hypothetical fully-real LmApiAdapter (0, still
    fake/narrowed-scope per the Tier 1 finding), above DebugAdapter (10,
    still fake) and GitAdapter (100, last resort). This is the highest
    priority REAL adapter that exists right now."""

    priority = 5

    def __init__(self, repo_path: Union[str, Path, None] = None):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._pending_dir = self.repo_path / ".agentguard" / "pending_captures"

    def _completed_capture_files(self) -> list:
        """Completed captures are named <session_id>__<uuid>.json.
        Prompt stashes awaiting a matching Stop event are named
        <session_id>__prompt.json - these are NOT ready to be captured yet
        and must be excluded.
        """
        if not self._pending_dir.exists():
            return []
        return sorted(
            p
            for p in self._pending_dir.glob("*__*.json")
            if not p.name.endswith("__prompt.json")
        )

    def is_available(self) -> bool:
        return len(self._completed_capture_files()) > 0

    def capture(self) -> CaptureEvent:
        files = self._completed_capture_files()
        if not files:
            raise RuntimeError(
                "ClaudeCodeHookAdapter.capture() called with nothing "
                "pending - check is_available() first"
            )

        # Oldest first (sorted() above sorts by filename, which sorts by
        # session_id then uuid - not strictly chronological across
        # sessions, but stable and good enough until this needs real
        # ordering guarantees).
        oldest = files[0]
        data = json.loads(oldest.read_text())

        event = CaptureEvent(
            adapter="claude_code_hook",
            timestamp=datetime.fromisoformat(data["captured_at"]),
            prompt=data["prompt"],
            response=data["response"],
            session_id=data["session_id"],
            developer=None,  # Claude Code hooks don't expose OS/git identity
            metadata={"cwd": data["cwd"], "source_file": str(oldest)},
        )

        oldest.unlink()  # consume it - don't emit the same capture twice
        return event
