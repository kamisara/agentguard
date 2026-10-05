"""
Sprint 6, Day 1 (updated Day 2: self-contained notes) validation script -
CI/CD Enforcement gate.

Tests against REAL commits in this repo, not mocks:
  1. A commit with a valid, signed, self-contained attestation -> VALID.
  2. A commit with no attestation at all -> MISSING (the normal case for
     any commit not made through AgentGuard).
  3. A commit whose embedded attestation was tampered with -> INVALID
     (same tamper-detection discipline as test_signing.py and
     test_intoto_dsse.py - the gate's whole purpose is catching exactly
     this).
  4. run_gate()'s exit code is 0 only when every commit passes, nonzero
     otherwise - this is the literal mechanism a real CI system uses to
     fail the job.
  5. The actual real-world scenario a live GitHub Actions run exposed:
     copying the whole repo to a completely different machine/path and
     confirming verification still succeeds - since embedded notes have
     zero external file dependency, this should now always work,
     regardless of .gitignore rules or which commit added which file.

All tests go through the REAL agentguard.auto_capture("git") code path
rather than reimplementing the sign+embed logic separately - this is
deliberate: the whole point of Sprint 6's self-containment fix was found
by testing the actual production path on a real CI runner, not by testing
building blocks in isolation. Reusing that exact path here keeps these
tests honest about what they're actually proving.

Run from inside the project root:
    python test_ci_gate.py
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ci_enforcement.gate import check_commit, run_gate, commits_in_range
from git_integration.notes import get_attestations_for_commit, NOTES_REF


def _cleanup_notes_ref(repo_path=None):
    subprocess.run(
        ["git", "update-ref", "-d", NOTES_REF],
        cwd=str(repo_path or Path.cwd()),
        capture_output=True,
    )


def _current_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip()


def _attest_current_commit():
    """Runs the REAL auto_capture('git') path - same code agentguard.py's
    CLI uses - so these tests exercise exactly what a real user/CI
    invocation does, not a parallel reimplementation."""
    import agentguard
    agentguard.auto_capture("git")


def test_valid_commit():
    print("=== Commit with a real, valid, self-contained attestation -> VALID ===")
    _cleanup_notes_ref()

    _attest_current_commit()
    commit_hash = _current_commit()

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
    print("=== Commit with a TAMPERED embedded attestation -> INVALID ===")
    _cleanup_notes_ref()

    _attest_current_commit()
    commit_hash = _current_commit()

    # Tamper with the note content directly - simulates someone editing
    # the embedded attestation after the fact. Since everything needed to
    # verify lives in the note now, tampering means rewriting the note
    # itself, not an external file.
    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 1
    tampered_entry = dict(entries[0])
    tampered_entry["attestation"] = dict(tampered_entry["attestation"])
    tampered_entry["attestation"]["developer_intent"] = "TAMPERED - should be caught"

    subprocess.run(
        ["git", "notes", f"--ref={NOTES_REF}", "remove", commit_hash],
        capture_output=True,
    )
    subprocess.run(
        ["git", "notes", f"--ref={NOTES_REF}", "add", "-m", json.dumps(tampered_entry), commit_hash],
        capture_output=True,
    )

    result = check_commit(commit_hash)
    assert result["status"] == "INVALID", result
    print(f"Commit {commit_hash[:12]}: {result['status']} (tampering correctly caught)")
    for a in result["attestations"]:
        print(f"  {a['attestation_id']}: {a['reason']}")
    print("PASS\n")


def test_gate_exit_codes():
    print("=== run_gate() exit codes match CI expectations ===")

    _cleanup_notes_ref()
    _attest_current_commit()
    commit_hash = _current_commit()

    exit_code_pass = run_gate(head=commit_hash)
    assert exit_code_pass == 0, f"expected 0 (pass), got {exit_code_pass}"
    print(f"Valid commit: exit code {exit_code_pass} (0 = CI passes)")

    _cleanup_notes_ref()
    exit_code_fail = run_gate(head=commit_hash)
    assert exit_code_fail != 0, f"expected nonzero (fail), got {exit_code_fail}"
    print(f"Missing attestation: exit code {exit_code_fail} (nonzero = CI fails)")
    print("PASS\n")


def test_self_contained_survives_different_machine():
    print("=== SPRINT 6 FIX, the real one: self-contained notes need ===")
    print("=== NOTHING but the note itself - proven across machines  ===")
    _cleanup_notes_ref()

    _attest_current_commit()
    commit_hash = _current_commit()

    # Simulate a genuinely different machine/CI runner: copy ONLY the
    # .git directory (which carries the notes ref) to a new location -
    # deliberately NOT copying .agentguard/, since that's exactly the
    # real-world gitignore situation that broke the old path-based
    # design. If self-containment actually works, verification should
    # succeed anyway, since nothing outside .git is needed anymore.
    sim_path = Path(tempfile.gettempdir()) / "agentguard_self_contained_test"
    if sim_path.exists():
        shutil.rmtree(sim_path)
    sim_path.mkdir(parents=True)
    shutil.copytree(Path.cwd() / ".git", sim_path / ".git")

    result = check_commit(commit_hash, repo_path=sim_path)
    assert result["status"] == "VALID", (
        f"expected VALID with ONLY .git copied (no .agentguard/ at all) - "
        f"got: {result}"
    )
    print(f"Verified from a location with ONLY .git present (no .agentguard/ directory)")
    print(f"Result: {result['status']}")

    shutil.rmtree(sim_path)
    print("PASS\n")


def test_range_check_multiple_commits():
    print("=== commits_in_range() resolves a real range correctly ===")
    _cleanup_notes_ref()

    # Don't assume the repo already has 2+ commits - make a real second
    # commit here so the range is guaranteed to resolve regardless of the
    # repo's prior state (same "first commit has no parent" consideration
    # GitAdapter already handles elsewhere).
    test_file = Path("ci_gate_range_test.tmp")
    test_file.write_text("range test")
    subprocess.run(["git", "add", str(test_file)], capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "test commit for range check"], capture_output=True)

    head = _current_commit()
    commits = commits_in_range("HEAD~1", "HEAD")
    assert commits == [head], f"expected [{head}], got {commits}"
    print(f"HEAD~1..HEAD resolved to: {commits}")

    test_file.unlink()
    subprocess.run(["git", "add", "-A"], capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "clean up range test file"], capture_output=True)
    print("PASS\n")


if __name__ == "__main__":
    test_valid_commit()
    test_missing_commit()
    test_tampered_attestation()
    test_gate_exit_codes()
    test_self_contained_survives_different_machine()
    test_range_check_multiple_commits()
    _cleanup_notes_ref()
    print("CI gate tests passed.")
