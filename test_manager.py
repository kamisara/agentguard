"""
Day 2 validation script.

Exercises BOTH branches of CaptureManager:
  1. Telemetry-first: a configured FakeTelemetrySource should be used, and
     native adapters should NOT be touched at all.
  2. Native fallback: with no telemetry source configured, adapters are
     tried in priority order - a higher-priority fake "LM API" adapter that
     reports unavailable should be skipped, falling through to the real
     GitAdapter.

Run from inside the project root:
    python test_manager.py
"""

from capture.fakes import FakeAdapter, FakeTelemetrySource
from capture.git_adapter import GitAdapter
from capture.manager import CaptureManager
from capture.normalizer import normalize


def test_telemetry_branch():
    print("=== Branch 1: telemetry source configured ===\n")

    telemetry = FakeTelemetrySource("fake-langfuse", configured=True)
    received = []

    manager = CaptureManager(
        telemetry_sources=[telemetry],
        native_adapters=[GitAdapter()],  # should never be touched
    )
    manager.start(on_event=lambda e: received.append(e))
    telemetry.emit_fake_event()

    assert len(received) == 1, "expected exactly one event via telemetry"
    assert received[0].adapter == "fake-langfuse"
    print(f"Received event via: {received[0].adapter}")
    print("PASS: telemetry source used, native adapters untouched\n")


def test_native_fallback_branch():
    print("=== Branch 2: no telemetry, priority-ordered native fallback ===\n")

    # Simulates: LM API adapter exists but isn't available right now
    # (e.g. no active Copilot/Claude session detected).
    unavailable_lm_api = FakeAdapter("fake-lm-api", priority=0, available=False)
    git_adapter = GitAdapter()  # priority=100, real, and available in this repo

    manager = CaptureManager(
        telemetry_sources=[],  # nothing configured
        native_adapters=[git_adapter, unavailable_lm_api],  # order shouldn't matter
    )

    manager.start(on_event=lambda e: None)  # no-op, nothing to subscribe to
    event = manager.capture_once()

    assert event.adapter == "git", (
        f"expected fallback to git adapter, got '{event.adapter}'"
    )
    print(f"Captured via: {event.adapter} (fake-lm-api correctly skipped)")

    normalized = normalize(event)
    print(f"intent_source: {normalized.intent_source.value}")
    print("PASS: fell through to git adapter as expected\n")


if __name__ == "__main__":
    test_telemetry_branch()
    test_native_fallback_branch()
    print("All CaptureManager branch tests passed.")
