#!/usr/bin/env python3
"""
AgentGuard - Sprint 3: Automatic Attestation Generation

Sprint 1's `capture` command asked the developer to type everything in by
hand. `auto-capture` replaces that: pulls a real CaptureEvent from one of
the Sprint 2B adapters (git/claude_code_hook/copilot_hook), normalizes it,
and generates a ContextualAttestation automatically - no manual entry.

Usage:
    python agentguard.py capture                 # Sprint 1: manual entry (still works)
    python agentguard.py auto-capture <source>    # Sprint 3: automatic, source = git|claude_code_hook|copilot_hook
    python agentguard.py otel-listen [seconds]    # Sprint 3: listen for real OTel spans, default 60s
    python agentguard.py list                     # list all recorded attestations (both schemas)
    python agentguard.py show <id>                # print one attestation in full
"""

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ATTESTATION_DIR = Path(".agentguard") / "attestations"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir():
    ATTESTATION_DIR.mkdir(parents=True, exist_ok=True)


def _prompt(label, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val or default or ""


def capture():
    """Interactively simulate one AI generation event and record it."""
    print("=== AgentGuard capture (Sprint 1: simulated interaction) ===\n")

    developer_intent = _prompt("Developer intent (what were you trying to do)")
    prompt_text = _prompt("Prompt sent to the AI")
    model = _prompt("AI model / agent name", default="simulated-model")
    provider = _prompt("Provider", default="simulated-provider")
    ai_output_summary = _prompt("Short summary of what the AI returned")
    reviewed = _prompt("Did a human review the output before commit? (y/n)", default="n")

    attestation_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    record = {
        "schema_version": "sprint1-v0",
        "attestation_id": attestation_id,
        "session_id": session_id,
        "timestamp": _now_iso(),
        "developer_intent": developer_intent,
        "prompt": prompt_text,
        "agent_identity": {
            "model": model,
            "provider": provider,
        },
        "ai_output_summary": ai_output_summary,
        "human_review_status": {
            "reviewed": reviewed.lower().startswith("y"),
            "reviewer": None,
        },
    }

    _ensure_dir()
    out_path = ATTESTATION_DIR / f"{attestation_id}.json"
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2)

    print(f"\n✔ Attestation captured -> {out_path}")
    return record


def list_attestations():
    _ensure_dir()
    files = sorted(ATTESTATION_DIR.glob("*.json"))
    if not files:
        print("No attestations recorded yet. Run: python agentguard.py capture")
        return
    for f in files:
        try:
            with open(f) as fh:
                record = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠ {f.name}: unreadable ({e}), skipping")
            continue

        attestation_id = record.get("attestation_id", f.stem)
        timestamp = record.get("timestamp", "unknown time")
        intent = record.get("developer_intent", "(no developer_intent field)")
        print(f"{attestation_id}  {timestamp}  intent=\"{intent[:50]}\"")


def show(attestation_id):
    _ensure_dir()
    matches = list(ATTESTATION_DIR.glob(f"{attestation_id}*.json"))
    if not matches:
        print(f"No attestation found matching id: {attestation_id}")
        return
    with open(matches[0]) as f:
        print(json.dumps(json.load(f), indent=2))


def auto_capture(source: str):
    """Sprint 3: pull a real event from an adapter, normalize, generate
    and store an attestation automatically. Replaces manual typing for
    the sources that support pull-based capture (git, the two hook
    adapters). OTel is push-based - see otel_listen() instead."""
    from capture.git_adapter import GitAdapter
    from capture.claude_code_hook_adapter import ClaudeCodeHookAdapter
    from capture.copilot_hook_adapter import CopilotHookAdapter
    from capture.normalizer import normalize
    from attestation.generator import generate_attestation
    from attestation.store import write_attestation

    adapters = {
        "git": GitAdapter(),
        "claude_code_hook": ClaudeCodeHookAdapter(),
        "copilot_hook": CopilotHookAdapter(),
    }

    adapter = adapters.get(source)
    if adapter is None:
        print(f"Unknown source '{source}'. Valid: {sorted(adapters)}")
        return

    if not adapter.is_available():
        print(f"No capture available from '{source}' right now.")
        if source in ("claude_code_hook", "copilot_hook"):
            print("(Nothing pending in .agentguard/pending_captures/ for this adapter.)")
        return

    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)
    out_path = write_attestation(attestation)

    print(f"✔ Attestation generated automatically from '{source}' -> {out_path}")
    print(f"  intent_source: {attestation.intent_source}")
    print(f"  developer_intent: {attestation.developer_intent[:80]}")
    if attestation.tool_invocations:
        print(f"  tool_invocations: {len(attestation.tool_invocations)}")


def otel_listen(seconds: int = 60):
    """Sprint 3: OTel is push-based (subscribe, not pull), so this starts
    the real receiver, listens for the given duration, and automatically
    attests every GenAI span that arrives - no manual entry, and no
    polling loop needed since CaptureManager's callback fires per event."""
    from capture.otel_telemetry_source import OtelGenAiTelemetrySource
    from capture.normalizer import normalize
    from attestation.generator import generate_attestation
    from attestation.store import write_attestation

    count = 0

    def on_event(event):
        nonlocal count
        normalized = normalize(event)
        attestation = generate_attestation(normalized)
        out_path = write_attestation(attestation)
        count += 1
        print(f"✔ [{count}] Attestation from otel_genai -> {out_path}")
        print(f"    developer_intent: {attestation.developer_intent[:80]}")

    source = OtelGenAiTelemetrySource()
    source.subscribe(on_event)
    print(f"Listening for real OTel GenAI spans at http://localhost:4318/v1/traces")
    print(f"({seconds}s - point your OTel-enabled agent's exporter here, then use it)")
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    finally:
        source.stop()
    print(f"\nStopped. {count} attestation(s) generated automatically this session.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "capture":
        capture()
    elif cmd == "auto-capture" and len(sys.argv) >= 3:
        auto_capture(sys.argv[2])
    elif cmd == "otel-listen":
        seconds = int(sys.argv[2]) if len(sys.argv) >= 3 else 60
        otel_listen(seconds)
    elif cmd == "list":
        list_attestations()
    elif cmd == "show" and len(sys.argv) >= 3:
        show(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()