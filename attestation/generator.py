"""
Generates a ContextualAttestation from a NormalizedEvent - the actual
"Automatic Attestation Generation" Sprint 3 goal: capture layer output
becomes an attestation record with no manual data entry, unlike
agentguard.py's original capture() command which asked the developer to
type everything in by hand.
"""

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from capture.types import NormalizedEvent

from .types import ContextualAttestation, SCHEMA_VERSION

# Sprint 3, Day 3. Naming heuristic, not a confirmed semantic signal - see
# types.py's retrieved_context docstring for the full honesty note. No
# transcript from any agent tested so far carries an explicit "this was a
# retrieval operation" field, so tool calls are classified by whether
# their name CONTAINS one of these substrings (case-insensitive).
_RETRIEVAL_TOOL_NAME_PATTERNS = (
    "view", "read", "search", "grep", "list", "glob", "fetch", "get",
)


def _is_retrieval_tool(tool_name: str) -> bool:
    name_lower = (tool_name or "").lower()
    return any(pattern in name_lower for pattern in _RETRIEVAL_TOOL_NAME_PATTERNS)


def _split_tool_calls(event: NormalizedEvent) -> tuple:
    """Returns (tool_invocations, retrieved_context) - two lists, split
    from event.tool_invocations by the naming heuristic above. Genuinely
    empty tuple of empties for adapters that don't populate tool calls at
    all (e.g. git)."""
    tool_invocations = []
    retrieved_context = []
    for tc in event.tool_invocations:
        entry = asdict(tc)
        if _is_retrieval_tool(tc.name):
            retrieved_context.append(entry)
        else:
            tool_invocations.append(entry)
    return tool_invocations, retrieved_context


def _build_prompt_lineage(event: NormalizedEvent) -> list:
    """Sprint 3, Day 3. PARTIAL - see types.py docstring for what's
    missing (injected tool outputs mid-chain). Only includes a system
    entry when the source adapter actually captured one - currently only
    otel_genai does, via the confirmed gen_ai.system_instructions
    attribute. Hook adapters never populate this."""
    lineage = []
    system_instructions = event.metadata.get("system_instructions")
    if system_instructions:
        lineage.append({"role": "system", "content": system_instructions})
    lineage.append({"role": "user", "content": event.developer_intent})
    return lineage


def generate_attestation(event: NormalizedEvent) -> ContextualAttestation:
    tool_invocations, retrieved_context = _split_tool_calls(event)

    return ContextualAttestation(
        schema_version=SCHEMA_VERSION,
        attestation_id=str(uuid.uuid4()),
        session_id=event.session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        adapter=event.adapter,
        developer_intent=event.developer_intent,
        intent_source=event.intent_source.value,
        prompt=event.developer_intent,  # legacy field name, same value
        ai_output_summary=event.ai_output,
        prompt_lineage=_build_prompt_lineage(event),
        agent_identity={
            "model": event.model,
            "adapter": event.adapter,
        },
        execution_environment={
            "session_id": event.session_id,
            "event_timestamp": event.timestamp.isoformat(),
        },
        tool_invocations=tool_invocations,
        retrieved_context=retrieved_context,
        human_review_status={"reviewed": False, "reviewer": None},  # placeholder
        policy_compliance_flags=[],  # placeholder, Sprint 8
        metadata=event.metadata,
    )
