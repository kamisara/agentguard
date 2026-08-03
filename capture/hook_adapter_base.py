"""
Shared base for adapters that read completed captures written by a hook
handler script (see hook_shared.py for the write side).

Both ClaudeCodeHookAdapter and CopilotHookAdapter are this same logic with
a different adapter_tag and priority - the read side has no per-agent
differences, unlike the transcript-parsing assumption noted in
hook_shared.py.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Union

from .interfaces import BaseAdapter
from .types import CaptureEvent


class FileBridgedHookAdapter(BaseAdapter):
    """priority must be set by the subclass. adapter_tag must match exactly
    what the corresponding hook_handler.py passes to hook_shared functions -
    this is what keeps two different agents' pending captures from being
    read by the wrong adapter."""

    adapter_tag: str  # set by subclass

    def __init__(self, repo_path: Union[str, Path, None] = None):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._pending_dir = self.repo_path / ".agentguard" / "pending_captures"

    def _completed_capture_files(self) -> list:
        """Completed captures are named <adapter_tag>__<session_id>__<uuid>.json.
        Prompt stashes awaiting a matching Stop event are named
        <adapter_tag>__<session_id>__prompt.json - excluded, not ready yet.
        Critically, only files matching THIS adapter's tag are considered -
        another agent's files sitting in the same directory are ignored."""
        if not self._pending_dir.exists():
            return []
        return sorted(
            p
            for p in self._pending_dir.glob(f"{self.adapter_tag}__*__*.json")
            if not p.name.endswith("__prompt.json")
        )

    def is_available(self) -> bool:
        return len(self._completed_capture_files()) > 0

    def capture(self) -> CaptureEvent:
        files = self._completed_capture_files()
        if not files:
            raise RuntimeError(
                f"{type(self).__name__}.capture() called with nothing "
                "pending - check is_available() first"
            )

        oldest = files[0]
        data = json.loads(oldest.read_text())

        event = CaptureEvent(
            adapter=self.adapter_tag,
            timestamp=datetime.fromisoformat(data["captured_at"]),
            prompt=data["prompt"],
            response=data["response"],
            session_id=data["session_id"],
            developer=None,
            metadata={"cwd": data["cwd"], "source_file": str(oldest)},
        )

        oldest.unlink()
        return event
