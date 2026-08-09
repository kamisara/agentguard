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


def generate_attestation(event: NormalizedEvent) -> ContextualAttestation:
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
        agent_identity={
            "model": event.model,
            "adapter": event.adapter,
        },
        execution_environment={
            "session_id": event.session_id,
            "event_timestamp": event.timestamp.isoformat(),
        },
        tool_invocations=[asdict(tc) for tc in event.tool_invocations],
        retrieved_context=[],  # placeholder, see types.py docstring
        human_review_status={"reviewed": False, "reviewer": None},  # placeholder
        policy_compliance_flags=[],  # placeholder, Sprint 8
        metadata=event.metadata,
    )
