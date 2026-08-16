"""
Signs and verifies ContextualAttestation records with Ed25519.

Canonicalization matters here: signing raw JSON text is fragile - the
same logical content can serialize to different byte sequences (key
order, whitespace) and produce a "signature mismatch" that has nothing to
do with tampering. Signs over json.dumps(data, sort_keys=True,
separators=(",", ":")) - deterministic byte output for the same logical
content, regardless of dict insertion order or formatting choices made
elsewhere in the codebase.

Signature format: detached, base64-encoded, written to a sibling
<attestation_id>.sig file (JSON containing the signature and which public
key to verify against) rather than embedded in the attestation JSON
itself - keeps the attestation file's shape unchanged for anything that
already reads it (agentguard.py list/show, existing tests), and matches
the "detached signature" pattern in-toto/Sigstore both use.
"""

import base64
import json
from pathlib import Path
from typing import Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .keys import load_private_key, load_public_key


def canonicalize(attestation_dict: dict) -> bytes:
    return json.dumps(attestation_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_attestation_dict(attestation_dict: dict, private_key: Ed25519PrivateKey) -> str:
    """Returns the base64-encoded signature over the canonical bytes."""
    message = canonicalize(attestation_dict)
    signature = private_key.sign(message)
    return base64.b64encode(signature).decode("ascii")


def verify_attestation_dict(
    attestation_dict: dict, signature_b64: str, public_key: Ed25519PublicKey
) -> bool:
    """Returns True if the signature is valid for this exact content,
    False on any mismatch - including tampering, wrong key, or corrupted
    signature. Does not raise; callers that need to distinguish failure
    reasons should catch InvalidSignature themselves if needed."""
    message = canonicalize(attestation_dict)
    signature = base64.b64decode(signature_b64)
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


def sig_path_for(attestation_path: Union[str, Path]) -> Path:
    attestation_path = Path(attestation_path)
    return attestation_path.with_suffix(".sig")


def _standard_public_key_path(attestation_path: Union[str, Path]) -> Path:
    """Derives .agentguard/keys/agentguard_public.pem from the
    attestation's own location (attestations/ and keys/ are sibling
    directories under the same .agentguard/ root) rather than trusting a
    path baked into the .sig file at signing time.

    This matters for real portability, not just tidiness: a .sig file's
    recorded public_key_path is an ABSOLUTE path from wherever signing
    happened. Move the repo, clone it somewhere else, or copy a .sig file
    from one machine's test environment into another machine's project
    (exactly what happened during development here) and that absolute
    path is meaningless. The standard-location convention doesn't have
    this problem - it's always correct as long as .agentguard/keys/ moved
    along with .agentguard/attestations/, which it always does since both
    are part of the same checked-in/synced directory."""
    attestation_path = Path(attestation_path)
    # attestation_path: .../.agentguard/attestations/<id>.json
    agentguard_dir = attestation_path.parent.parent  # .../.agentguard
    return agentguard_dir / "keys" / "agentguard_public.pem"


def write_signature(
    attestation_path: Union[str, Path],
    attestation_dict: dict,
    private_key_path: Union[str, Path],
    public_key_path: Union[str, Path],
) -> Path:
    private_key = load_private_key(private_key_path)
    signature_b64 = sign_attestation_dict(attestation_dict, private_key)

    sig_data = {
        "attestation_id": attestation_dict.get("attestation_id"),
        "algorithm": "Ed25519",
        "signature": signature_b64,
        # Kept for reference/debugging only - NOT the primary lookup
        # mechanism during verification, see _standard_public_key_path
        # above and verify_signature_file below.
        "public_key_path": str(public_key_path),
    }

    out_path = sig_path_for(attestation_path)
    out_path.write_text(json.dumps(sig_data, indent=2))
    return out_path


def verify_signature_file(
    attestation_path: Union[str, Path], public_key_path: Union[str, Path] = None
) -> dict:
    """Reads both the attestation and its .sig file, verifies, and
    returns a result dict rather than just True/False - a verification
    tool needs to report WHY something failed (missing sig file, key
    mismatch, tampered content), not just a boolean.

    Key lookup order: explicit public_key_path argument (if given) ->
    standard-location convention (.agentguard/keys/ next to
    .agentguard/attestations/) -> the path recorded in the .sig file, as
    a last-resort fallback for a key stored somewhere non-standard. The
    standard location is checked BEFORE the recorded path deliberately -
    see _standard_public_key_path's docstring for why trusting the
    recorded path first is fragile."""
    attestation_path = Path(attestation_path)
    sig_path = sig_path_for(attestation_path)

    if not attestation_path.exists():
        return {"valid": False, "reason": "attestation file not found"}
    if not sig_path.exists():
        return {"valid": False, "reason": "signature file not found (unsigned)"}

    attestation_dict = json.loads(attestation_path.read_text())
    sig_data = json.loads(sig_path.read_text())

    if public_key_path:
        key_path = Path(public_key_path)
    else:
        standard_path = _standard_public_key_path(attestation_path)
        if standard_path.exists():
            key_path = standard_path
        else:
            recorded_path = sig_data.get("public_key_path")
            key_path = Path(recorded_path) if recorded_path else None

    if not key_path or not key_path.exists():
        return {"valid": False, "reason": f"public key not found: {key_path}"}

    public_key = load_public_key(key_path)
    valid = verify_attestation_dict(attestation_dict, sig_data["signature"], public_key)

    return {
        "valid": valid,
        "reason": "signature valid" if valid else "signature does NOT match content (tampered or wrong key)",
        "algorithm": sig_data.get("algorithm"),
        "public_key_path": str(key_path),
    }
