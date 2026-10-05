"""
CI/CD Enforcement gate (Sprint 6, Day 1).

Checks that a commit (or range of commits) has a valid, signed attestation
attached via git notes before allowing CI to proceed. This is the actual
enforcement mechanism the proposal calls for: "a GitHub Actions / GitLab
CI gate that verifies the presence, integrity, and policy compliance of
contextual attestations before code progresses to build."

SCOPE for Day 1: presence + signature integrity only. Custom policy rules
(e.g. "AI-authored commits need human review", "certain files require
attestation") are explicitly Sprint 8 (Policy Engine) scope - not
implemented here, not silently faked as "policy compliance".

REAL GIT GOTCHA, confirmed via search before building this (not assumed):
git notes live under refs/notes/*, a ref namespace separate from
branches/tags. actions/checkout does NOT fetch them, even with
fetch-depth: 0 - an explicit `git fetch origin refs/notes/*:refs/notes/*`
step is required. Getting this wrong would make the gate silently report
"MISSING" for every commit, even ones with real attestations on the
actual remote - a false negative that actively defeats the point of the
gate. Handled explicitly in .github/workflows/agentguard-gate.yml.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Union

# Allows running this script directly (as CI does: `python ci_enforcement/gate.py`)
# without the project root already being on sys.path. Without this, the
# sibling packages below (git_integration, signing) fail to import when
# this file is invoked as a script rather than imported as a module -
# found by testing the actual CI invocation pattern directly, not just
# via test_ci_gate.py's module-level imports, which don't hit this path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from git_integration.notes import get_attestations_for_commit
from signing.signer import verify_embedded_entry


def _run_git(args: list, repo_path: Union[str, Path, None] = None) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(repo_path or Path.cwd()),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def commits_in_range(
    base: str, head: str, repo_path: Union[str, Path, None] = None
) -> List[str]:
    """Returns commit hashes from base..head, oldest first. If base is
    empty/None, returns just [head] resolved to a full hash - a
    single-commit check, useful for a simple "gate the latest commit"
    workflow without needing to resolve a full PR diff range."""
    if not base:
        return [_run_git(["rev-parse", head], repo_path)]
    output = _run_git(["log", "--reverse", "--format=%H", f"{base}..{head}"], repo_path)
    return [line for line in output.splitlines() if line]


def check_commit(commit_hash: str, repo_path: Union[str, Path, None] = None) -> dict:
    """Returns a result dict for one commit: whether it has attestations
    attached, and whether every attached one passes signature
    verification. SPRINT 6 FIX: verification is now fully self-contained
    (verify_embedded_entry) - the git note itself carries the attestation
    content, signature, and public key, with zero dependency on any
    external file existing in the checkout. This replaced an earlier
    design that stored only a path reference, which broke in real CI
    testing (gitignored files, commit-ordering mismatches - see
    git_integration/notes.py's module docstring for the full story)."""
    entries = get_attestations_for_commit(commit_hash, repo_path)
    if not entries:
        return {"commit": commit_hash, "status": "MISSING", "attestations": []}

    results = []
    for entry in entries:
        verify_result = verify_embedded_entry(entry)
        results.append({
            "attestation_id": entry.get("attestation_id"),
            "valid": verify_result["valid"],
            "reason": verify_result["reason"],
        })

    all_valid = all(r["valid"] for r in results)
    status = "VALID" if all_valid else "INVALID"
    return {"commit": commit_hash, "status": status, "attestations": results}


def run_gate(
    base: str = None,
    head: str = "HEAD",
    repo_path: Union[str, Path, None] = None,
    require_all: bool = True,
) -> int:
    """Runs the gate over the given commit range, prints a report, returns
    an exit code (0 = pass, nonzero = fail) - this exit code is exactly
    what a CI system uses to fail the job/block the merge.
    require_all=True (the default and only exposed behavior for Day 1)
    means every commit in range must have a valid attestation attached;
    MISSING and INVALID both fail the gate."""
    commits = commits_in_range(base, head, repo_path)
    if not commits:
        print("No commits to check.")
        return 0

    failed = False
    print(f"AgentGuard CI Gate - checking {len(commits)} commit(s)\n")
    for commit_hash in commits:
        result = check_commit(commit_hash, repo_path)
        short = commit_hash[:12]
        if result["status"] == "MISSING":
            print(f"✘ {short}  MISSING - no attestation attached")
            if require_all:
                failed = True
        elif result["status"] == "INVALID":
            print(f"✘ {short}  INVALID - attached attestation failed verification")
            for a in result["attestations"]:
                if not a["valid"]:
                    print(f"    {a['attestation_id']}: {a['reason']}")
            failed = True
        else:
            print(f"✔ {short}  VALID - {len(result['attestations'])} attestation(s) verified")

    print()
    if failed:
        print("GATE FAILED")
        return 1
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AgentGuard CI/CD attestation gate")
    parser.add_argument(
        "--base", default=None,
        help="base ref (exclusive) - omit to check only --head as a single commit"
    )
    parser.add_argument("--head", default="HEAD", help="head ref (inclusive), default HEAD")
    args = parser.parse_args()
    sys.exit(run_gate(args.base, args.head))
