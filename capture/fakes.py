"""
Fake capture sources - for testing CaptureManager's branching logic only.

These are NOT real integrations. A FakeAdapter/FakeTelemetrySource exists
purely to prove the manager correctly chooses between telemetry-first and
native-fallback paths, and correctly orders adapters by priority. Real
Debug/LM API adapters replace these incrementally in later sprints - see
README.
"""

from datetime import datetime, timezone
from typing import Callable, Optional

from .interfaces import BaseAdapter, TelemetrySource
from .types import CaptureEvent


class FakeAdapter(BaseAdapter):
    """A configurable fake native adapter for testing fallback ordering."""

    def __init__(self, name: str, priority: int, available: bool = True):
        self.name = name
        self.priority = priority
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def capture(self) -> CaptureEvent:
        return CaptureEvent(
            adapter=self.name,
            timestamp=datetime.now(timezone.utc),
            prompt=f"[fake] prompt captured by {self.name}",
            response=f"[fake] response captured by {self.name}",
            metadata={"fake": True},
        )


class FakeTelemetrySource(TelemetrySource):
    """A configurable fake telemetry source for testing the
    telemetry-takes-priority branch of CaptureManager."""

    def __init__(self, name: str, configured: bool = True):
        self.name = name
        self._configured = configured
        self.subscribed_callback: Optional[Callable] = None

    def is_configured(self) -> bool:
        return self._configured

    def subscribe(self, on_event: Callable[[CaptureEvent], None]) -> None:
        self.subscribed_callback = on_event

    def emit_fake_event(self) -> None:
        """Test helper: simulate the external system pushing an event."""
        if self.subscribed_callback is None:
            raise RuntimeError(f"{self.name} was never subscribed to")
        self.subscribed_callback(
            CaptureEvent(
                adapter=self.name,
                timestamp=datetime.now(timezone.utc),
                prompt=f"[fake] prompt from telemetry source {self.name}",
                response=f"[fake] response from telemetry source {self.name}",
                metadata={"fake": True, "telemetry": True},
            )
        )
