"""
Capture source interfaces.

Two distinct contracts, not one, because native adapters and telemetry
sources have fundamentally different lifecycles:

  - BaseAdapter is PULL-based. The manager asks "are you available?", then
    asks for a single capture. This fits git, debug-log scraping, and the
    LM API - all request/response by nature.

  - TelemetrySource is PUSH-based. External instrumentation (Langfuse,
    Phoenix, OpenTelemetry/OpenInference exporters) emits spans on its own
    schedule, whenever the instrumented application produces one. There is
    no single call that returns "the" event - forcing this through
    BaseAdapter's capture() would mean either polling a buffer or
    arbitrarily blocking on whichever span arrives first.

Do not collapse these into one interface. See proposal Section 4.2 for the
full rationale.
"""

from abc import ABC, abstractmethod
from typing import Callable

from .types import CaptureEvent


class BaseAdapter(ABC):
    """A pull-based native capture source.

    `priority` determines fallback order inside CaptureManager - LOWER
    values are checked first. Assign priorities deliberately based on
    capture fidelity, not implementation convenience:

        LM API adapter   -> priority 0  (highest fidelity: real prompt/response)
        Debug adapter     -> priority 10 (real prompt/response, but scraped)
        Git adapter       -> priority 100 (last resort: inferred, not captured)
    """

    priority: int

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this adapter can capture something right now.

        Must be cheap and side-effect-free - CaptureManager may call this
        on every adapter before finding one that's available.
        """
        raise NotImplementedError

    @abstractmethod
    def capture(self) -> CaptureEvent:
        """Perform the actual capture. Only called after is_available()
        has returned True for this adapter."""
        raise NotImplementedError


class TelemetrySource(ABC):
    """A push-based external instrumentation source.

    Unlike BaseAdapter, this does not return a single CaptureEvent. It
    registers a callback that fires whenever the external system (Langfuse,
    Phoenix, an OTel/OpenInference exporter, etc.) produces a new span, for
    as long as the source remains subscribed.
    """

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this telemetry source is set up and reachable
        (e.g. API key present, exporter endpoint responding). Checked once
        at startup, not per-event."""
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, on_event: Callable[[CaptureEvent], None]) -> None:
        """Register a callback to be invoked for every event this source
        produces. Does not block and does not return a value - events
        arrive asynchronously via the callback for the lifetime of the
        process."""
        raise NotImplementedError
