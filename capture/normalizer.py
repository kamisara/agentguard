"""
Context Normalizer: CaptureEvent -> NormalizedEvent.

This is the one place adapter-specific quirks get resolved. Nothing after
this point (attestation generation, Sprint 3+) should ever branch on
`event.adapter == "git"` or similar - if you find yourself wanting to do
that downstream, the mapping belongs here instead.
"""

from .types import CaptureEvent, NormalizedEvent, IntentSource

# Adapters whose "prompt" field is an explicit developer instruction
# (typed/spoken directly to the AI). Everything else is treated as inferred
# intent reconstructed after the fact (e.g. from a commit message).
#
# NOTE: this set will grow as real adapters (lm_api, debug) are implemented
# in later sprints. Deliberately explicit rather than "everything except
# git" so adding a new adapter forces a conscious decision about which
# bucket it belongs in.
EXPLICIT_INTENT_ADAPTERS = {"lm_api", "debug", "lsp", "claude_code_hook", "copilot_hook"}


def _resolve_intent_source(adapter: str) -> IntentSource:
    return (
        IntentSource.EXPLICIT
        if adapter in EXPLICIT_INTENT_ADAPTERS
        else IntentSource.INFERRED
    )


def normalize(event: CaptureEvent) -> NormalizedEvent:
    return NormalizedEvent(
        developer_intent=event.prompt,
        intent_source=_resolve_intent_source(event.adapter),
        ai_output=event.response,
        model=event.model,
        session_id=event.session_id,
        tool_invocations=event.tool_calls,
        timestamp=event.timestamp,
        adapter=event.adapter,
        metadata=event.metadata,
    )
