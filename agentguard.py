#!/usr/bin/env python3
"""
AgentGuard - Sprint 1: Capture

Goal: answer "Can I capture AI generation metadata before a Git commit?"

No crypto. No anomaly detection. Just capture.

Workflow simulated:
    You ask AI  -->  AgentGuard records metadata  -->  writes an attestation (JSON)

Usage:
    python agentguard.py capture      # interactively record one AI interaction
    python agentguard.py list         # list all recorded attestations
    python agentguard.py show <id>    # print one attestation in full
"""

import json
import sys
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
        with open(f) as fh:
            record = json.load(fh)
        print(f"{record['attestation_id']}  {record['timestamp']}  intent=\"{record['developer_intent'][:50]}\"")


def show(attestation_id):
    _ensure_dir()
    matches = list(ATTESTATION_DIR.glob(f"{attestation_id}*.json"))
    if not matches:
        print(f"No attestation found matching id: {attestation_id}")
        return
    with open(matches[0]) as f:
        print(json.dumps(json.load(f), indent=2))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "capture":
        capture()
    elif cmd == "list":
        list_attestations()
    elif cmd == "show" and len(sys.argv) >= 3:
        show(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()