"""
Sprint 6, Day 1 validation script - CI/CD Enforcement gate.

Tests against REAL commits in this repo, not mocks:
  1. A commit with a valid, signed, attached attestation -> VALID.
  2. A commit with no attestation at all -> MISSING (the normal case for
     any commit not made through AgentGuard).
  3. A commit whose attached attestation file was tampered with on disk
     AFTER signing -> INVALID (same tamper-detection discipline as
     test_signing.py and test_intoto_dsse.py - the gate's whole purpose
     is catching exactly this).
  4. run_gate()'s exit code is 0 only when every commit passes, nonzero
     otherwise - this is the literal mechanism a real CI system uses to
     fail the job, so it's not just an implementation detail to get right.

Run from inside the project root:
    python test_ci_gate.py
"""

import json
import subprocess
from pathlib import Path

from ci_enforcement.gate import check_commit, run_gate, commits_in_range
from git_integration.notes import attach_attestation_note, NOTES_REF
from capture.git_adapter import GitAdapter
from capture.normalizer import normalize
from attestation.generator import generate_attestation
from attestation.store import write_and_sign_attestation


def _cleanup_notes_ref(repo_path=None):
    subprocess.run(
        ["git", "update-ref", "-d", NOTES_REF],
        cwd=str(repo_path or Path.cwd()),
        capture_output=True,
    )


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return result.stdout.strip()


def test_valid_commit():
    print("=== Commit with a real, valid, attached attestation -> VALID ===")
    _cleanup_notes_ref()

    adapter = GitAdapter()
    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)
    attestation_path, _ = write_and_sign_attestation(attestation)

    commit_hash = _current_commit()
    attach_attestation_note(commit_hash, attestation.attestation_id, attestation_path)

    result = check_commit(commit_hash)
    assert result["status"] == "VALID", result
    print(f"Commit {commit_hash[:12]}: {result['status']}")
    print("PASS\n")


def test_missing_commit():
    print("=== Commit with no attestation at all -> MISSING ===")
    _cleanup_notes_ref()

    commit_hash = _current_commit()
    result = check_commit(commit_hash)
    assert result["status"] == "MISSING", result
    print(f"Commit {commit_hash[:12]}: {result['status']} (correct - no note attached)")
    print("PASS\n")


def test_tampered_attestation():
    print("=== Commit with a TAMPERED attached attestation -> INVALID ===")
    _cleanup_notes_ref()

    adapter = GitAdapter()
    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)
    attestation_path, _ = write_and_sign_attestation(attestation)

    commit_hash = _current_commit()
    attach_attestation_note(commit_hash, attestation.attestation_id, attestation_path)

    # Tamper with the attestation file on disk, same as the real
    # tampering scenario tested in test_signing.py - this is exactly
    # the case the gate exists to catch.
    data = json.loads(Path(attestation_path).read_text())
    data["developer_intent"] = "TAMPERED - this should be caught by the gate"
    Path(attestation_path).write_text(json.dumps(data))

    result = check_commit(commit_hash)
    assert result["status"] == "INVALID", result
    print(f"Commit {commit_hash[:12]}: {result['status']} (tampering correctly caught)")
    for a in result["attestations"]:
        print(f"  {a['attestation_id']}: {a['local_key_reason']}")
    print("PASS\n")


def test_gate_exit_codes():
    print("=== run_gate() exit codes match CI expectations ===")

    # Passing case: valid attestation attached.
    _cleanup_notes_ref()
    adapter = GitAdapter()
    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)
    attestation_path, _ = write_and_sign_attestation(attestation)
    commit_hash = _current_commit()
    attach_attestation_note(commit_hash, attestation.attestation_id, attestation_path)

    exit_code_pass = run_gate(head=commit_hash)
    assert exit_code_pass == 0, f"expected 0 (pass), got {exit_code_pass}"
    print(f"Valid commit: exit code {exit_code_pass} (0 = CI passes)")

    # Failing case: no attestation attached.
    _cleanup_notes_ref()
    exit_code_fail = run_gate(head=commit_hash)
    assert exit_code_fail != 0, f"expected nonzero (fail), got {exit_code_fail}"
    print(f"Missing attestation: exit code {exit_code_fail} (nonzero = CI fails)")
    print("PASS\n")


def test_range_check_multiple_commits():
    print("=== commits_in_range() resolves a real range correctly ===")
    _cleanup_notes_ref()

    # Don't assume the repo already has 2+ commits (a fresh/shallow repo
    # might only have one, in which case HEAD~1 doesn't exist at all -
    # the same "first commit has no parent" edge case GitAdapter already
    # handles elsewhere). Make a real second commit here so the range is
    # guaranteed to resolve regardless of the repo's prior state.
    test_file = Path("ci_gate_range_test.tmp")
    test_file.write_text("range test")
    subprocess.run(["git", "add", str(test_file)], capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "test commit for range check"],
        capture_output=True,
    )

    head = _current_commit()
    commits = commits_in_range("HEAD~1", "HEAD")
    assert commits == [head], f"expected [{head}], got {commits}"
    print(f"HEAD~1..HEAD resolved to: {commits}")

    test_file.unlink()
    subprocess.run(["git", "add", "-A"], capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "clean up range test file"],
        capture_output=True,
    )
    print("PASS\n")


if __name__ == "__main__":
    test_valid_commit()
    test_missing_commit()
    test_tampered_attestation()
    test_gate_exit_codes()
    test_range_check_multiple_commits()
    _cleanup_notes_ref()
    print("CI gate tests passed.")
