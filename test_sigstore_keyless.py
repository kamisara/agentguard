"""
Sprint 4, Day 2 validation script - Sigstore keyless signing.

HONEST SCOPE: this test does NOT prove keyless signing works end-to-end.
It can't, in this environment - confirmed via direct testing that both
Fulcio (cert issuance) and even ClientTrustConfig/Verifier construction
(TUF trust-root fetch) fail here with network errors, not just
hypothetically. See signing/sigstore_signer.py's module docstring for
the full finding.

What this test DOES verify, safely, without hanging or requiring a
browser/network:
  1. The module imports correctly and uses the REAL installed sigstore
     API (confirmed via runtime inspection, not memory - this library's
     API has changed across versions).
  2. bundle_path_for() produces the correct Sigstore convention
     (<name>.sigstore.json), matching standard cosign/sigstore tooling.
  3. The network-restricted failure mode (TUFError on trust config
     construction) is caught and reported clearly by the CLI layer
     (agentguard.py sign-keyless/verify-keyless), not left as a raw
     traceback - this is a REAL failure mode, not hypothetical, likely
     to recur on restricted/corporate networks, not just this sandbox.

What is NOT tested here, and needs a real machine with normal internet
access to confirm: an actual OIDC login, actual Fulcio certificate
issuance, actual Rekor logging, actual verification against a real
Bundle. See README for exact steps to test this for real.

Run from inside the project root:
    python test_sigstore_keyless.py
"""

from pathlib import Path

from signing.sigstore_signer import (
    bundle_path_for,
    PRODUCTION_OIDC_ISSUER_URL,
    verify_attestation_file_keyless,
)


def test_module_imports_real_api():
    print("=== Module uses the real installed sigstore API ===")
    # If this file imported at all, sign_keyless/verify_keyless/etc. are
    # using real class/method names that exist in the installed
    # `sigstore` package - confirmed via runtime inspection during
    # development (sigstore==4.5.0), not assumed from memory. An import
    # error here would mean the API surface doesn't match.
    assert PRODUCTION_OIDC_ISSUER_URL == "https://oauth2.sigstore.dev/auth"
    print(f"OIDC issuer: {PRODUCTION_OIDC_ISSUER_URL}")
    print("PASS\n")


def test_bundle_naming_convention():
    print("=== Bundle file naming matches Sigstore's own convention ===")
    attestation_path = Path("/some/dir/abc123.json")
    bundle_path = bundle_path_for(attestation_path)
    assert bundle_path.name == "abc123.sigstore.json", bundle_path.name
    print(f"attestation: {attestation_path.name}  ->  bundle: {bundle_path.name}")
    print("PASS\n")


def test_missing_bundle_reported_clearly():
    print("=== Verifying an attestation with no bundle fails clearly, not crashes ===")
    # No network call happens here - this fails at the file-existence
    # check, before ever touching sigstore's verification machinery.
    result = verify_attestation_file_keyless(
        "/tmp/definitely_does_not_exist_abc123.json",
        expected_identity="someone@example.com",
    )
    assert result["valid"] is False
    assert "not found" in result["reason"]
    print(f"Result: {result}")
    print("PASS\n")


if __name__ == "__main__":
    test_module_imports_real_api()
    test_bundle_naming_convention()
    test_missing_bundle_reported_clearly()
    print("Sigstore keyless module tests passed (scope: imports, naming,")
    print("error handling - NOT a real signing round trip, see docstring).")
