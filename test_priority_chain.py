"""
Day 3 validation script.

Tests the real three-adapter priority chain: LmApiAdapter (0) > DebugAdapter
(10) > GitAdapter (100). Both LM API and Debug are still fakes (gated by
env vars so they're never accidentally "available"), but this exercises the
actual adapter classes that will later be swapped to real implementations -
not the generic FakeAdapter from fakes.py, which was only ever meant to
prove CaptureManager's branching logic in isolation.

Run from inside the project root:
    python test_priority_chain.py
"""

import os

from capture.debug_adapter import DebugAdapter, _FAKE_AVAILABLE_ENV_VAR as DEBUG_ENV
from capture.git_adapter import GitAdapter
from capture.lm_api_adapter import LmApiAdapter, _FAKE_AVAILABLE_ENV_VAR as LM_API_ENV
from capture.manager import CaptureManager


def _clear_fake_flags():
    os.environ.pop(LM_API_ENV, None)
    os.environ.pop(DEBUG_ENV, None)


def _build_manager() -> CaptureManager:
    # Passed in deliberately unsorted order - CaptureManager sorts by
    # priority itself, so this also checks that sort isn't accidentally
    # relying on caller-provided order.
    return CaptureManager(
        telemetry_sources=[],
        native_adapters=[GitAdapter(), LmApiAdapter(), DebugAdapter()],
    )


def test_all_fakes_off_falls_to_git():
    print("=== Case 1: LM API off, Debug off -> should fall to Git ===")
    _clear_fake_flags()
    event = _build_manager().capture_once()
    assert event.adapter == "git", f"expected git, got {event.adapter}"
    print(f"Captured via: {event.adapter}\nPASS\n")


def test_lm_api_wins_when_available():
    print("=== Case 2: LM API on -> should win over Debug and Git ===")
    _clear_fake_flags()
    os.environ[LM_API_ENV] = "1"
    os.environ[DEBUG_ENV] = "1"  # also on, to prove LM API still wins
    event = _build_manager().capture_once()
    assert event.adapter == "lm_api", f"expected lm_api, got {event.adapter}"
    print(f"Captured via: {event.adapter}\nPASS\n")
    _clear_fake_flags()


def test_debug_wins_when_lm_api_unavailable():
    print("=== Case 3: LM API off, Debug on -> should fall to Debug, not Git ===")
    _clear_fake_flags()
    os.environ[DEBUG_ENV] = "1"
    event = _build_manager().capture_once()
    assert event.adapter == "debug", f"expected debug, got {event.adapter}"
    print(f"Captured via: {event.adapter}\nPASS\n")
    _clear_fake_flags()


if __name__ == "__main__":
    test_all_fakes_off_falls_to_git()
    test_lm_api_wins_when_available()
    test_debug_wins_when_lm_api_unavailable()
    print("All priority chain tests passed.")
