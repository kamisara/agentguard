"""
Day 1 validation script.

Run against a real git repo to confirm the CaptureEvent -> NormalizedEvent
pipeline holds up against actual commit data, not invented examples.

This script only prints - it does NOT write into .agentguard/attestations/.
It used to (a leftover from before the real attestation schema existed in
Sprint 3), which caused a real bug: its ad-hoc NormalizedEvent dump had no
`attestation_id` field, so agentguard.py's `list` command crashed on it
after this script had been run. Producing real attestations is
attestation/generator.py's job now - use `python agentguard.py auto-capture
git` for that, not this script.

Usage:
    python test_git_adapter.py [path/to/repo]
    (defaults to the current directory's repo if no path given)
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import sys

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
    print(
        "(This script only validates the capture pipeline - it does not "
        "write an attestation. Use 'python agentguard.py auto-capture git' "
        "for that.)"
    )


if __name__ == "__main__":
    main()
