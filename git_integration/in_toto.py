"""
Builds a real in-toto v1 Statement binding a ContextualAttestation to the
specific git commit it came from, wraps it in a DSSE envelope, writes it
using the real .intoto.jsonl convention.

Statement shape, confirmed via the in-toto Attestation Framework's own
spec and real published examples (not assumed):

    {
      "_type": "https://in-toto.io/Statement/v1",
      "subject": [{"name": ..., "digest": {"gitCommit": "<sha1>"}}],
      "predicateType": "<URI>",
      "predicate": {...}
    }

subject.digest uses "gitCommit" as the digest algorithm name - this
matches real usage seen in SLSA's own resolvedDependencies examples for
referencing a git commit (a sha1-hash-shaped value under a
git-specific key, distinct from a generic "sha1" digest of arbitrary
file content).

predicateType is a custom URI identifying AgentGuard's own predicate
schema (ContextualAttestation) - this is the correct, spec-sanctioned way
to attest custom data: in-toto explicitly allows any predicateType URI,
consumers are expected to ignore predicate types they don't recognize
(the "monotonic principle" from the spec) rather than reject them.

File convention: <attestation_id>.intoto.jsonl - matches the extension
real in-toto/SLSA tooling uses for a DSSE-wrapped attestation
(slsa-verifier, cosign attest, and the Attestation Framework's own Bundle
spec all use this suffix).
"""

import json
from pathlib import Path
from typing import Union

from .dsse import create_envelope, verify_envelope

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
AGENTGUARD_PREDICATE_TYPE = "https://agentguard.dev/ContextualAttestation/v1"


def build_statement(attestation_dict: dict, commit_hash: str) -> dict:
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": commit_hash[:12],
                "digest": {"gitCommit": commit_hash},
            }
        ],
        "predicateType": AGENTGUARD_PREDICATE_TYPE,
        "predicate": attestation_dict,
    }


def intoto_path_for(attestation_path: Union[str, Path]) -> Path:
    attestation_path = Path(attestation_path)
    return attestation_path.with_suffix("").with_suffix(".intoto.jsonl")


def write_intoto_attestation(
    attestation_path: Union[str, Path],
    attestation_dict: dict,
    commit_hash: str,
    private_key_path: Union[str, Path],
) -> Path:
    from signing.keys import load_private_key

    statement = build_statement(attestation_dict, commit_hash)
    private_key = load_private_key(private_key_path)
    envelope = create_envelope(statement, private_key, key_id=str(private_key_path))

    out_path = intoto_path_for(attestation_path)
    out_path.write_text(json.dumps(envelope))
    return out_path


def verify_intoto_attestation(
    attestation_path: Union[str, Path], public_key_path: Union[str, Path] = None
) -> dict:
    """Same standard-location-first key lookup as signing/signer.py's
    verify_signature_file() - see that module for why trusting a baked-in
    path is fragile (real bug found and fixed via live testing)."""
    from signing.keys import load_public_key
    from signing.signer import _standard_public_key_path

    attestation_path = Path(attestation_path)
    intoto_path = intoto_path_for(attestation_path)

    if not intoto_path.exists():
        return {"valid": False, "reason": "no .intoto.jsonl file found", "statement": None}

    envelope = json.loads(intoto_path.read_text())

    if public_key_path:
        key_path = Path(public_key_path)
    else:
        standard_path = _standard_public_key_path(attestation_path)
        key_path = standard_path if standard_path.exists() else None

    if not key_path or not key_path.exists():
        return {"valid": False, "reason": f"public key not found: {key_path}", "statement": None}

    public_key = load_public_key(key_path)
    return verify_envelope(envelope, public_key)
