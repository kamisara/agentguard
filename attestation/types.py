"""
Contextual Attestation schema (Sprint 3).

Field set follows the proposal's Section 4.3 "What Contextual Attestation
records" list: developer intent, prompt lineage, agent identity, execution
environment, retrieved context, tool invocations, human review status,
policy compliance flags. Not every field is fully populated yet - honesty
notes below mark exactly what's real data vs. a placeholder for a later
sprint, so nobody mistakes an empty list for "nothing happened" instead
of "not implemented yet".

schema_version bumped to "sprint3-v1" - the original agentguard.py
capture() command used "sprint1-v0" for its manually-typed record. Both
schemas coexist; list_attestations()/show() in agentguard.py read fields
common to both (developer_intent, prompt, timestamp) so old and new
records both display correctly.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional

SCHEMA_VERSION = "sprint3-v1"


@dataclass
class ContextualAttestation:
    schema_version: str
    attestation_id: str
    session_id: Optional[str]
    timestamp: str  # ISO 8601, when the attestation was generated
    adapter: str  # which capture mechanism produced the underlying event

    developer_intent: str
    intent_source: str  # "explicit" | "inferred" - carried through from NormalizedEvent

    # Legacy field names kept for backward compat with agentguard.py's
    # existing list_attestations()/show() commands, which were built
    # against the sprint1-v0 manual schema.
    prompt: str
    ai_output_summary: str

    prompt_lineage: list  # Sprint 3, Day 3. PARTIAL, stated honestly: a
                            # list of {"role", "content"} entries. Includes
                            # a system entry ONLY when the source adapter
                            # captured one (currently: otel_genai via
                            # gen_ai.system_instructions - confirmed
                            # attribute name, real when present) plus the
                            # developer's prompt as a user entry. Does NOT
                            # yet include injected tool outputs mid-chain
                            # (the proposal's fuller definition) - that
                            # needs multi-turn conversation tracking this
                            # project doesn't do yet. Hook adapters never
                            # populate a system entry - they don't capture
                            # system prompt content at all right now.

    agent_identity: dict  # {model, adapter} - provider is None unless an
                           # adapter populates it; no current adapter does

    execution_environment: dict  # {session_id, event_timestamp} - real
                                   # fields only. temperature/inference
                                   # endpoint are proposal-scoped fields no
                                   # adapter currently captures - NOT
                                   # included here rather than faked as None
                                   # in every record; add when a real
                                   # source exists.

    tool_invocations: list  # REAL for otel_genai (confirmed live data,
                              # 2026-08-09) and both hook adapters
                              # (Copilot: confirmed live data, 2026-08-04;
                              # Claude Code: unconfirmed assumed shape,
                              # never live-tested). Sprint 3 Day 3: now
                              # split from retrieved_context by a NAME-
                              # PATTERN HEURISTIC (see generator.py
                              # _is_retrieval_tool) - no adapter or
                              # transcript exposes an explicit "this was a
                              # retrieval call" flag, so this is a guess
                              # based on tool naming conventions, not a
                              # confirmed signal. Genuinely empty [] for
                              # git (no tool concept at all).

    retrieved_context: list  # Sprint 3, Day 3: REAL, not a placeholder
                               # anymore - tool calls whose name matches a
                               # read/retrieval pattern (view, read,
                               # search, grep, list, glob, fetch, get) are
                               # classified here instead of
                               # tool_invocations. STATED HONESTLY: this
                               # is a naming heuristic, not a confirmed
                               # semantic signal - no transcript from any
                               # agent tested so far includes an explicit
                               # "is this a retrieval operation" field.
                               # Could misclassify a tool literally named
                               # e.g. "read_and_delete_file".

    human_review_status: dict  # PLACEHOLDER. {"reviewed": False,
                                 # "reviewer": None} always, for every
                                 # record - no adapter or workflow captures
                                 # actual human review yet. This is
                                 # future scope (dashboard/review workflow),
                                 # not implemented by Sprint 3.

    policy_compliance_flags: list  # PLACEHOLDER, explicitly deferred to
                                     # Sprint 8 (Policy Engine) per the
                                     # sprint plan - always [] for now.

    metadata: dict  # raw passthrough from CaptureEvent.metadata, for
                     # traceability/debugging - not part of the formal
                     # schema, but useful to keep alongside it.

    def to_dict(self) -> dict:
        return asdict(self)
