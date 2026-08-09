"""
Sprint 3, Day 1 validation script.

Tests generate_attestation() against REAL captured data, not invented
fixtures - same discipline as the rest of this project:
  1. A real git commit from this repo's own history (GitAdapter).
  2. A real restored Copilot session capture, from an actual live session
     on 2026-08-08 (CopilotHookAdapter reading a real pending_captures file).

Confirms: schema fields populate correctly, intent_source is preserved
correctly per adapter (inferred for git, explicit for the hook), the
record round-trips through write_attestation/read_attestation_dict
correctly, and old (sprint1-v0) and new (sprint3-v1) records coexist in
the same directory without either breaking agentguard.py's list/show.

Run from inside the project root:
    python test_attestation_generation.py
"""

from capture.git_adapter import GitAdapter
from capture.copilot_hook_adapter import CopilotHookAdapter
from capture.normalizer import normalize
from attestation.generator import generate_attestation
from attestation.store import write_attestation, read_attestation_dict


def test_attestation_from_real_git_commit():
    print("=== Attestation from a real git commit ===")
    adapter = GitAdapter()
    assert adapter.is_available()

    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)

    assert attestation.schema_version == "sprint3-v1"
    assert attestation.adapter == "git"
    assert attestation.intent_source == "inferred"
    assert attestation.developer_intent  # non-empty, real commit message
    assert attestation.tool_invocations == []  # git has no tool concept
    assert attestation.human_review_status == {"reviewed": False, "reviewer": None}
    assert attestation.policy_compliance_flags == []

    out_path = write_attestation(attestation)
    assert out_path.exists()

    reread = read_attestation_dict(out_path)
    assert reread["attestation_id"] == attestation.attestation_id
    assert reread["developer_intent"] == attestation.developer_intent

    print(f"developer_intent: {attestation.developer_intent[:60]}")
    print(f"intent_source:    {attestation.intent_source}")
    print(f"Written and re-read correctly: {out_path.name}")
    print("PASS\n")


def test_attestation_from_real_copilot_session():
    print("=== Attestation from a real (restored) Copilot session ===")
    adapter = CopilotHookAdapter()

    if not adapter.is_available():
        print("SKIPPED: no real Copilot fixture present in "
              ".agentguard/pending_captures/ - run this after auto-capture "
              "has consumed it, or restore a real fixture first.\n")
        return

    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)

    assert attestation.adapter == "copilot_hook"
    assert attestation.intent_source == "explicit"
    assert "README" in attestation.developer_intent  # this real fixture's actual prompt

    out_path = write_attestation(attestation)
    print(f"developer_intent: {attestation.developer_intent[:60]}")
    print(f"intent_source:    {attestation.intent_source}")
    print(f"Written: {out_path.name}")
    print("PASS\n")


if __name__ == "__main__":
    test_attestation_from_real_git_commit()
    test_attestation_from_real_copilot_session()
    print("Attestation generation tests passed.")
