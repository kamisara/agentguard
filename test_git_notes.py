"""
Sprint 5, Day 1 validation script (updated Sprint 6: self-contained notes).

Tests git notes integration against a REAL git repo (this project's own),
not a mock:
  1. Attach a self-contained attestation to the current HEAD commit,
     confirm it's retrievable AND its embedded signature verifies.
  2. Attach a SECOND attestation to the same commit - confirms
     `git notes append` behavior (multiple AI-assisted edits before one
     commit is a real, expected case), not overwriting.
  3. A commit with no note at all returns [], not an error - this is the
     normal case for any commit not made through AgentGuard.
  4. Full pipeline: real git capture -> attestation -> auto_capture's
     actual note-attaching code path (not just the notes module directly).

SPRINT 6 CHANGE: attach_attestation_note() now takes the full attestation
dict + signature + public key PEM, not an id + external path - see
git_integration/notes.py's module docstring for why (a real bug found via
live CI testing: path-based notes broke on gitignored files and
commit-ordering mismatches).

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
from signing.keys import generate_keypair, load_private_key, public_key_to_pem_string, load_public_key
from signing.signer import sign_attestation_dict, verify_embedded_entry


def _cleanup_notes_ref(repo_path=None):
    """Test isolation: remove the agentguard notes ref between test runs
    so leftover notes from a previous run don't affect assertions about
    exact counts."""
    subprocess.run(
        ["git", "update-ref", "-d", NOTES_REF],
        cwd=str(repo_path or Path.cwd()),
        capture_output=True,
    )


def _fake_signed_attestation(attestation_id: str, intent: str):
    """Builds a minimal real attestation dict + real Ed25519 signature +
    real public key PEM - everything a real auto_capture() call would
    produce, just without going through the full capture pipeline, since
    these tests are about the notes mechanism itself, not attestation
    generation (covered elsewhere)."""
    import tempfile
    key_dir = Path(tempfile.gettempdir()) / f"agentguard_notes_test_keys_{attestation_id}"
    private_path, public_path = generate_keypair(key_dir)
    private_key = load_private_key(private_path)
    public_key_pem = public_key_to_pem_string(load_public_key(public_path))

    attestation_dict = {"attestation_id": attestation_id, "developer_intent": intent}
    signature_b64 = sign_attestation_dict(attestation_dict, private_key)
    return attestation_dict, signature_b64, public_key_pem


def test_attach_and_retrieve():
    print("=== Attach one self-contained attestation to real HEAD, retrieve + verify it ===")
    _cleanup_notes_ref()

    commit_hash = get_current_commit_hash()
    assert commit_hash, "expected a real commit hash from this repo"
    print(f"HEAD: {commit_hash}")

    attestation_dict, signature_b64, public_key_pem = _fake_signed_attestation(
        "attestation-abc", "test intent"
    )
    attach_attestation_note(commit_hash, attestation_dict, signature_b64, public_key_pem)

    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 1, entries
    assert entries[0]["attestation_id"] == "attestation-abc"

    # This is the actual point of the Sprint 6 fix: verification needs
    # NOTHING but this entry - no external file lookup at all.
    result = verify_embedded_entry(entries[0])
    assert result["valid"] is True, result
    print(f"Retrieved and verified: {entries[0]['attestation_id']} -> {result}")
    print("PASS\n")


def test_multiple_attestations_same_commit():
    print("=== Multiple attestations on the SAME commit (append, not overwrite) ===")
    _cleanup_notes_ref()

    commit_hash = get_current_commit_hash()
    a1, s1, k1 = _fake_signed_attestation("attestation-1", "first")
    a2, s2, k2 = _fake_signed_attestation("attestation-2", "second")
    attach_attestation_note(commit_hash, a1, s1, k1)
    attach_attestation_note(commit_hash, a2, s2, k2)

    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 2, f"expected 2 (append should not overwrite), got {len(entries)}"
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
    print("=== Full pipeline: real auto_capture('git') attaches a self-contained note ===")
    _cleanup_notes_ref()

    import agentguard
    agentguard.auto_capture("git")

    commit_hash = get_current_commit_hash()
    entries = get_attestations_for_commit(commit_hash)
    assert len(entries) == 1, (
        f"expected auto_capture to have attached exactly one note to HEAD, got {len(entries)}"
    )

    from signing.signer import verify_embedded_entry
    result = verify_embedded_entry(entries[0])
    assert result["valid"] is True, result
    print(f"auto_capture('git') attached a self-contained, verified entry: {result}")
    print("PASS\n")


if __name__ == "__main__":
    test_attach_and_retrieve()
    test_multiple_attestations_same_commit()
    test_commit_with_no_note()
    test_full_pipeline_via_auto_capture()
    _cleanup_notes_ref()  # leave the repo clean
    print("Git notes integration tests passed.")
