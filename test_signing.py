"""
Sprint 4, Day 1 validation script.

Tests real Ed25519 signing/verification - not just "does it run", but the
actual security properties that matter:
  1. A genuinely signed attestation verifies as valid.
  2. Tampering with the content AFTER signing is detected (this is the
     entire point of signing - if this test doesn't exist, signing isn't
     actually proven to do anything).
  3. Verifying against the WRONG public key is rejected.
  4. Full pipeline: real git capture -> attestation -> sign -> verify,
     using write_and_sign_attestation() as agentguard.py actually calls it.

Run from inside the project root:
    python test_signing.py
"""

import json
import shutil
import tempfile
from pathlib import Path

from signing.keys import generate_keypair, load_private_key, load_public_key
from signing.signer import (
    sign_attestation_dict,
    verify_attestation_dict,
    write_signature,
    verify_signature_file,
)

from capture.git_adapter import GitAdapter
from capture.normalizer import normalize
from attestation.generator import generate_attestation
from attestation.store import write_and_sign_attestation


TEST_DIR = Path(tempfile.gettempdir()) / "agentguard_signing_test"


def _clean():
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True)


def test_sign_and_verify_valid():
    print("=== Sign and verify a genuine attestation ===")
    _clean()
    private_path, public_path = generate_keypair(TEST_DIR)
    private_key = load_private_key(private_path)
    public_key = load_public_key(public_path)

    attestation_dict = {"attestation_id": "abc123", "developer_intent": "Fix the bug"}
    signature = sign_attestation_dict(attestation_dict, private_key)

    assert verify_attestation_dict(attestation_dict, signature, public_key) is True
    print("Signature verifies correctly against unmodified content.")
    print("PASS\n")


def test_tamper_detection():
    print("=== Tampering after signing is detected (the actual point of signing) ===")
    _clean()
    private_path, public_path = generate_keypair(TEST_DIR)
    private_key = load_private_key(private_path)
    public_key = load_public_key(public_path)

    original = {"attestation_id": "abc123", "developer_intent": "Fix the bug"}
    signature = sign_attestation_dict(original, private_key)

    # Simulate tampering: someone edits the attestation file after it was
    # signed, e.g. to hide what a prompt actually asked for.
    tampered = dict(original)
    tampered["developer_intent"] = "Fix the bug (actually: exfiltrate secrets)"

    assert verify_attestation_dict(original, signature, public_key) is True
    assert verify_attestation_dict(tampered, signature, public_key) is False
    print("Original content: verifies TRUE (correct)")
    print("Tampered content: verifies FALSE (correct - tampering caught)")
    print("PASS\n")


def test_wrong_key_rejected():
    print("=== Verifying against the wrong public key is rejected ===")
    _clean()
    private_path_a, public_path_a = generate_keypair(TEST_DIR / "a")
    _, public_path_b = generate_keypair(TEST_DIR / "b")

    private_key_a = load_private_key(private_path_a)
    public_key_b = load_public_key(public_path_b)  # wrong key on purpose

    attestation_dict = {"attestation_id": "abc123", "developer_intent": "Fix the bug"}
    signature = sign_attestation_dict(attestation_dict, private_key_a)

    assert verify_attestation_dict(attestation_dict, signature, public_key_b) is False
    print("Signed with key A, verified against key B: correctly rejected.")
    print("PASS\n")


def test_file_based_round_trip():
    print("=== File-based signature round trip (write_signature / verify_signature_file) ===")
    _clean()
    # Mirrors the REAL convention: keys/ and attestations/ as siblings
    # under .agentguard/ - this is what _standard_public_key_path relies
    # on to find the key without trusting a possibly-stale absolute path
    # recorded in the .sig file (see signer.py for why that matters -
    # this was a real bug found via live testing on a real machine).
    agentguard_root = TEST_DIR / ".agentguard"
    attestations_dir = agentguard_root / "attestations"
    attestations_dir.mkdir(parents=True)

    private_path, public_path = generate_keypair(TEST_DIR)

    attestation_dict = {"attestation_id": "file-test-1", "developer_intent": "Add tests"}
    attestation_path = attestations_dir / "file-test-1.json"
    attestation_path.write_text(json.dumps(attestation_dict))

    sig_path = write_signature(attestation_path, attestation_dict, private_path, public_path)
    assert sig_path.exists()
    print(f"Signature file written: {sig_path.name}")

    # Verify WITHOUT passing public_key_path explicitly - proves the
    # standard-location lookup works on its own, which is how
    # agentguard.py's real verify/verify-all commands call this.
    result = verify_signature_file(attestation_path)
    assert result["valid"] is True, result
    print(f"Verification result: {result}")

    # Now tamper with the attestation file on disk directly - the file
    # verification path should catch this too, not just the in-memory one.
    tampered = json.loads(attestation_path.read_text())
    tampered["developer_intent"] = "Add tests (tampered after signing)"
    attestation_path.write_text(json.dumps(tampered))

    result_after_tamper = verify_signature_file(attestation_path)
    assert result_after_tamper["valid"] is False
    print(f"After on-disk tampering: {result_after_tamper}")
    print("PASS\n")


def test_portable_across_machines():
    print("=== Signature verifies even with a stale/foreign recorded public_key_path ===")
    # This is the actual bug found via live testing: a .sig file created
    # on one machine (or in a different directory) has an absolute
    # public_key_path baked in that's meaningless elsewhere. Verification
    # must not depend on that path being correct - only on the standard
    # .agentguard/keys/ location actually existing alongside the
    # attestation.
    _clean()
    agentguard_root = TEST_DIR / ".agentguard"
    attestations_dir = agentguard_root / "attestations"
    attestations_dir.mkdir(parents=True)

    private_path, public_path = generate_keypair(TEST_DIR)
    attestation_dict = {"attestation_id": "portable-test", "developer_intent": "test"}
    attestation_path = attestations_dir / "portable-test.json"
    attestation_path.write_text(json.dumps(attestation_dict))

    sig_path = write_signature(attestation_path, attestation_dict, private_path, public_path)

    # Simulate the exact real bug: corrupt the recorded path to something
    # that doesn't exist on THIS machine, the way a .sig file copied from
    # a different environment would.
    sig_data = json.loads(sig_path.read_text())
    sig_data["public_key_path"] = "/some/machine/that/does/not/exist/public.pem"
    sig_path.write_text(json.dumps(sig_data))

    result = verify_signature_file(attestation_path)
    assert result["valid"] is True, (
        f"expected valid=True (standard-location lookup should ignore the "
        f"bogus recorded path), got: {result}"
    )
    print(f"Recorded path was bogus, but standard-location lookup found the real key.")
    print(f"Result: {result}")
    print("PASS\n")


def test_full_pipeline_real_git_capture():
    print("=== Full pipeline: real git capture -> attestation -> sign -> verify ===")
    adapter = GitAdapter()
    assert adapter.is_available()

    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)

    attestation_path, sig_path = write_and_sign_attestation(attestation)
    assert attestation_path.exists()
    assert sig_path.exists()

    result = verify_signature_file(attestation_path)
    assert result["valid"] is True, result
    print(f"Real attestation: {attestation_path.name}")
    print(f"Signature:        {sig_path.name}")
    print(f"Verification:     {result}")
    print("PASS\n")


if __name__ == "__main__":
    test_sign_and_verify_valid()
    test_tamper_detection()
    test_wrong_key_rejected()
    test_file_based_round_trip()
    test_portable_across_machines()
    test_full_pipeline_real_git_capture()
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    print("Signing tests passed.")
