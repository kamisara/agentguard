"""
Sprint 5, Day 1 validation script.

Tests git notes integration against a REAL git repo (this project's own),
not a mock:
  1. Attach an attestation reference to the current HEAD commit, confirm
     it's retrievable.
  2. Attach a SECOND attestation reference to the same commit - confirms
     `git notes append` behavior (multiple AI-assisted edits before one
     commit is a real, expected case), not overwriting.
  3. A commit with no note at all returns [], not an error - this is the
     normal case for any commit not made through AgentGuard.
  4. Full pipeline: real git capture -> attestation -> auto_capture's
     actual note-attaching code path (not just the notes module directly).

Run from inside the project root:
    python test_git_notes.py
"""

import subprocess
from pathlib import Path

from git_integration.notes import (
    attach_attestation_note,
    get_attestations_for_commit,
    get_current_commit_hash,
    NOTES_REF,
)


def _cleanup_notes_ref(repo_path=None):
    """Test isolation: remove the agentguard notes ref between test runs
    so leftover notes from a previous run don't affect assertions about
    exact counts."""
    subprocess.run(
        ["git", "update-ref", "-d", NOTES_REF],
        cwd=str(repo_path or Path.cwd()),
        capture_output=True,
    )


def test_attach_and_retrieve():
    print("=== Attach one attestation reference to real HEAD, retrieve it ===")
    _cleanup_notes_ref()

    commit_hash = get_current_commit_hash()
    assert commit_hash, "expected a real commit hash from this repo"
    print(f"HEAD: {commit_hash}")

    attach_attestation_note(commit_hash, "attestation-abc", ".agentguard/attestations/abc.json")

    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 1, entries
    assert entries[0]["attestation_id"] == "attestation-abc"
    print(f"Retrieved: {entries}")
    print("PASS\n")


def test_multiple_attestations_same_commit():
    print("=== Multiple attestations on the SAME commit (append, not overwrite) ===")
    _cleanup_notes_ref()

    commit_hash = get_current_commit_hash()
    attach_attestation_note(commit_hash, "attestation-1", "path1.json")
    attach_attestation_note(commit_hash, "attestation-2", "path2.json")

    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 2, f"expected 2 (append should not overwrite), got {entries}"
    ids = {e["attestation_id"] for e in entries}
    assert ids == {"attestation-1", "attestation-2"}
    print(f"Both attestations present: {ids}")
    print("PASS\n")


def test_commit_with_no_note():
    print("=== Commit with no note returns [], not an error ===")
    _cleanup_notes_ref()

    # A real commit that (after cleanup) genuinely has no agentguard note.
    commit_hash = get_current_commit_hash()
    entries = get_attestations_for_commit(commit_hash)
    assert entries == [], entries
    print("Correctly returned [] for a commit with no attached attestation.")
    print("PASS\n")


def test_full_pipeline_via_auto_capture():
    print("=== Full pipeline: real auto_capture('git') attaches a note automatically ===")
    _cleanup_notes_ref()

    import agentguard
    agentguard.auto_capture("git")

    commit_hash = get_current_commit_hash()
    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 1, (
        f"expected auto_capture to have attached exactly one note to HEAD, got {entries}"
    )
    print(f"auto_capture('git') automatically attached: {entries[0]}")
    print("PASS\n")


if __name__ == "__main__":
    test_attach_and_retrieve()
    test_multiple_attestations_same_commit()
    test_commit_with_no_note()
    test_full_pipeline_via_auto_capture()
    _cleanup_notes_ref()  # leave the repo clean
    print("Git notes integration tests passed.")
