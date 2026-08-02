"""
CaptureManager: the single entry point that decides where a CaptureEvent
comes from.

Decision order, per proposal Section 4.2:
  1. Telemetry Source Ingestion, if any source is configured (push-based,
     highest fidelity when present - the org already instruments their
     agent traffic, so we get it essentially for free).
  2. Native Capture Adapters, in priority order, if no telemetry source is
     configured (pull-based fallback ladder: LM API > Debug > Git).

These are genuinely different branches, not two flavors of the same thing -
see interfaces.py for why BaseAdapter and TelemetrySource aren't unified
into one contract.
"""

import logging
from typing import Callable, List, Optional

from .interfaces import BaseAdapter, TelemetrySource
from .types import CaptureEvent

logger = logging.getLogger(__name__)


class NoCaptureSourceAvailable(Exception):
    """Raised when no telemetry source is configured and no native adapter
    reports itself available. This is a real failure, not a silent no-op -
    callers should decide how to handle it (retry, alert, skip this event)."""


class CaptureManager:
    def __init__(
        self,
        telemetry_sources: Optional[List[TelemetrySource]] = None,
        native_adapters: Optional[List[BaseAdapter]] = None,
    ):
        self.telemetry_sources = telemetry_sources or []
        # Sort once at construction time, not on every capture - adapter
        # priority doesn't change at runtime.
        self.native_adapters = sorted(
            native_adapters or [], key=lambda a: a.priority
        )

    def start(self, on_event: Callable[[CaptureEvent], None]) -> None:
        """Subscribes to the first configured telemetry source, if any.

        Important: this only checks telemetry sources. If none are
        configured, native adapters are NOT started here - they're
        pull-based and have no "start listening" concept. Use capture_once()
        to pull from them on demand (e.g. triggered by a git post-commit
        hook, a CLI invocation, etc.).
        """
        for source in self.telemetry_sources:
            if source.is_configured():
                logger.info("Using telemetry source: %s", type(source).__name__)
                source.subscribe(on_event)
                return

        logger.info(
            "No telemetry source configured; native adapters will be used "
            "on-demand via capture_once()."
        )

    def capture_once(self) -> CaptureEvent:
        """Pulls a single CaptureEvent from the first available native
        adapter, in priority order.

        Only call this when no telemetry source is active - if start()
        subscribed to a telemetry source, events arrive via that callback
        instead, and calling capture_once() alongside it would produce
        events through two uncoordinated paths.
        """
        for adapter in self.native_adapters:
            if adapter.is_available():
                logger.info("Using native adapter: %s", type(adapter).__name__)
                return adapter.capture()

        raise NoCaptureSourceAvailable(
            "No telemetry source configured and no native adapter is "
            "available. Adapters checked: "
            f"{[type(a).__name__ for a in self.native_adapters]}"
        )
