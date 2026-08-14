"""
Sprint 3, Day 3 validation script.

Tests the two additions to generate_attestation():
  1. retrieved_context / tool_invocations split by the naming heuristic -
     proves BOTH directions, not just retrieval (test_tool_calls_end_to_end.py
     already covers "view" -> retrieved_context; this adds an edit-type
     tool call staying in tool_invocations, using real Copilot field
     names/shape).
  2. prompt_lineage - a system_instructions entry from otel_genai metadata
     (real field, confirmed from Copilot's OTel emission), and the
     no-system-entry case for hook-sourced events (honest: hooks don't
     capture system prompts at all).

Run from inside the project root:
    python test_attestation_classification.py
"""

from datetime import datetime, timezone

from capture.types import NormalizedEvent, IntentSource, ToolCall
from attestation.generator import generate_attestation


def _make_event(tool_calls, metadata=None, developer_intent="test intent"):
    return NormalizedEvent(
        developer_intent=developer_intent,
        intent_source=IntentSource.EXPLICIT,
        ai_output="test output",
        timestamp=datetime.now(timezone.utc),
        adapter="copilot_hook",
        tool_invocations=tool_calls,
        metadata=metadata or {},
    )


def test_action_tool_stays_in_tool_invocations():
    print("=== Non-retrieval tool call correctly stays in tool_invocations ===")
    # "edit" doesn't match any retrieval pattern (view/read/search/grep/
    # list/glob/fetch/get) - real tool name shape from Copilot's own
    # toolRequests structure.
    event = _make_event([ToolCall(name="edit", args={"path": "README.md"}, output="File updated")])
    attestation = generate_attestation(event)

    assert len(attestation.tool_invocations) == 1, attestation.tool_invocations
    assert len(attestation.retrieved_context) == 0, attestation.retrieved_context
    assert attestation.tool_invocations[0]["name"] == "edit"
    print(f"tool_invocations:  {attestation.tool_invocations}")
    print(f"retrieved_context: {attestation.retrieved_context} (correctly empty)")
    print("PASS\n")


def test_mixed_tool_calls_split_correctly():
    print("=== Mixed retrieval + action calls split correctly ===")
    event = _make_event([
        ToolCall(name="grep", args={"pattern": "TODO"}, output="3 matches"),
        ToolCall(name="edit", args={"path": "x.py"}, output="Updated"),
        ToolCall(name="list_dir", args={"path": "."}, output="a.py, b.py"),
    ])
    attestation = generate_attestation(event)

    retrieval_names = {tc["name"] for tc in attestation.retrieved_context}
    action_names = {tc["name"] for tc in attestation.tool_invocations}

    assert retrieval_names == {"grep", "list_dir"}, retrieval_names
    assert action_names == {"edit"}, action_names
    print(f"retrieved_context names: {retrieval_names}")
    print(f"tool_invocations names:  {action_names}")
    print("PASS\n")


def test_prompt_lineage_with_system_instructions():
    print("=== prompt_lineage includes system entry when otel captured one ===")
    event = _make_event(
        [],
        metadata={"system_instructions": "You are a careful coding assistant."},
        developer_intent="Fix the bug in parser.py",
    )
    attestation = generate_attestation(event)

    assert len(attestation.prompt_lineage) == 2
    assert attestation.prompt_lineage[0] == {
        "role": "system", "content": "You are a careful coding assistant."
    }
    assert attestation.prompt_lineage[1] == {
        "role": "user", "content": "Fix the bug in parser.py"
    }
    print(f"prompt_lineage: {attestation.prompt_lineage}")
    print("PASS\n")


def test_prompt_lineage_without_system_instructions():
    print("=== prompt_lineage is user-only when no system data captured (hooks) ===")
    event = _make_event([], metadata={}, developer_intent="Add a comment to README")
    attestation = generate_attestation(event)

    assert len(attestation.prompt_lineage) == 1, attestation.prompt_lineage
    assert attestation.prompt_lineage[0]["role"] == "user"
    print(f"prompt_lineage: {attestation.prompt_lineage} (no system entry - honest, hooks don't capture this)")
    print("PASS\n")


if __name__ == "__main__":
    test_action_tool_stays_in_tool_invocations()
    test_mixed_tool_calls_split_correctly()
    test_prompt_lineage_with_system_instructions()
    test_prompt_lineage_without_system_instructions()
    print("Attestation classification/lineage tests passed.")
