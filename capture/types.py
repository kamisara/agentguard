"""
Core types for the AgentGuard Capture Layer (Sprint 2B).

Everything an adapter or telemetry source produces gets converted into a
CaptureEvent. The Context Normalizer then converts CaptureEvent -> NormalizedEvent.
Nothing downstream of the normalizer should ever look at adapter-specific fields.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


@dataclass
class ToolCall:
    name: str
    args: dict = field(default_factory=dict)
    output: Optional[str] = None


@dataclass
class CaptureEvent:
    """Raw output of a single capture, before normalization.

    Adapters are allowed to leave fields as None - they capture what they
    can see. Don't force adapters to guess at fields they don't have.
    """

    adapter: str
    timestamp: datetime
    prompt: str
    response: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    session_id: Optional[str] = None
    developer: Optional[str] = None
    tool_calls: list = field(default_factory=list)  # list[ToolCall]
    metadata: dict = field(default_factory=dict)


class IntentSource(str, Enum):
    """Where the "developer intent" field actually came from.

    This matters: a git commit message is an INFERENCE about intent made
    after the fact. A captured prompt (Debug/LM API adapters) is the
    developer's actual, explicit instruction. Downstream consumers
    (evaluation, dashboard, eventually ML) need to be able to tell these
    apart and weight them differently - collapsing them into one untyped
    string loses that signal.
    """

    EXPLICIT = "explicit"
    INFERRED = "inferred"


@dataclass
class NormalizedEvent:
    """Output of the Context Normalizer. This is the schema everything after
    Sprint 2B (attestation generation, signing, CI/CD, dashboard) consumes.
    Adding a field here is a schema change - do it deliberately, not
    adapter by adapter.
    """

    developer_intent: str
    intent_source: IntentSource
    ai_output: str
    timestamp: datetime
    adapter: str
    model: Optional[str] = None
    session_id: Optional[str] = None
    tool_invocations: list = field(default_factory=list)  # list[ToolCall]
    metadata: dict = field(default_factory=dict)
