"""
Day 1 validation script.

Run against a real git repo to confirm the CaptureEvent -> NormalizedEvent
pipeline holds up against actual commit data, not invented examples.

Usage:
    python -m agentguard.test_git_adapter [path/to/repo]
    (defaults to the current directory's repo if no path given)
"""

import json
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from capture.git_adapter import capture_from_git
from capture.normalizer import normalize


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def main():
    repo_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    print(f"\n=== Capturing last commit from: {repo_path} ===\n")

    raw_event = capture_from_git(repo_path)
    print("CaptureEvent:")
    print(json.dumps(asdict(raw_event), indent=2, default=_json_default))

    normalized = normalize(raw_event)
    print("\nNormalizedEvent:")
    print(json.dumps(asdict(normalized), indent=2, default=_json_default))

    print(
        f"\nintent_source = \"{normalized.intent_source.value}\" "
        f"(expect \"inferred\" for git)\n"
    )

    # Write to the existing attestation convention so this plugs straight
    # into what agentguard.py already does (capture/list/show against
    # .agentguard/attestations/<uuid>.json)
    out_dir = repo_path / ".agentguard" / "attestations"
    out_dir.mkdir(parents=True, exist_ok=True)
    attestation_id = str(uuid.uuid4())
    out_path = out_dir / f"{attestation_id}.json"
    out_path.write_text(
        json.dumps(asdict(normalized), indent=2, default=_json_default)
    )
    print(f"Wrote attestation: {out_path}")


if __name__ == "__main__":
    main()
