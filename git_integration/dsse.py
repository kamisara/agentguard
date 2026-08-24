"""
DSSE (Dead Simple Signing Envelope) - the transport layer in-toto
attestations use, per the in-toto Attestation Framework spec (confirmed
via the framework's own spec docs and real examples, not assumed):

    Envelope: {"payloadType": "application/vnd.in-toto+json",
               "payload": "<base64(Statement JSON)>",
               "signatures": [{"keyid": ..., "sig": "<base64(signature)>"}]}

CRITICAL DETAIL, easy to get wrong: DSSE does NOT sign the raw payload
bytes directly. It signs the PAE (Pre-Authentication Encoding) - a
specific framing that binds the payload type into what's actually signed,
preventing a signature meant for one payload type from being replayed as
valid for a different one. Per the DSSE spec:

    PAE(type, body) = "DSSEv1" + SP + LEN(type) + SP + type +
                       SP + LEN(body) + SP + body

where LEN is the ASCII decimal length and SP is a single space byte.
Signing the raw payload instead of the PAE would produce a
non-interoperable, non-spec-compliant signature - it would "work" against
our own verifier but fail against any real in-toto/DSSE tooling (cosign,
in-toto verifier, etc.), which is exactly the kind of subtle wrongness
this project has learned to check for directly rather than assume away.
"""

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

INTOTO_PAYLOAD_TYPE = "application/vnd.in-toto+json"


def pae(payload_type: str, payload: bytes) -> bytes:
    """Pre-Authentication Encoding, per the DSSE spec."""
    type_bytes = payload_type.encode("utf-8")
    return b" ".join([
        b"DSSEv1",
        str(len(type_bytes)).encode("ascii"), type_bytes,
        str(len(payload)).encode("ascii"), payload,
    ])


def create_envelope(
    statement_dict: dict, private_key: Ed25519PrivateKey, key_id: str = ""
) -> dict:
    """Builds a real DSSE envelope: canonicalizes the statement, signs its
    PAE (not the raw bytes), returns the envelope structure ready to
    serialize as JSON."""
    payload = json.dumps(statement_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(pae(INTOTO_PAYLOAD_TYPE, payload))

    return {
        "payloadType": INTOTO_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [
            {"keyid": key_id, "sig": base64.b64encode(signature).decode("ascii")}
        ],
    }


def verify_envelope(envelope: dict, public_key: Ed25519PublicKey) -> dict:
    """Verifies a DSSE envelope's signature against its PAE, returns
    {"valid": bool, "reason": str, "statement": dict|None}. Does not
    raise - callers get a structured result, same pattern as
    signing/signer.py's verify_signature_file()."""
    payload_type = envelope.get("payloadType")
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures", [])

    if payload_type != INTOTO_PAYLOAD_TYPE:
        return {"valid": False, "reason": f"unexpected payloadType: {payload_type}", "statement": None}
    if not signatures:
        return {"valid": False, "reason": "no signatures present", "statement": None}

    try:
        payload = base64.b64decode(payload_b64)
    except Exception as e:
        return {"valid": False, "reason": f"payload not valid base64: {e}", "statement": None}

    message = pae(payload_type, payload)
    signature_b64 = signatures[0]["sig"]

    try:
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, message)
    except InvalidSignature:
        return {"valid": False, "reason": "signature does NOT match content (tampered or wrong key)", "statement": None}
    except Exception as e:
        return {"valid": False, "reason": f"verification error: {type(e).__name__}: {e}", "statement": None}

    try:
        statement = json.loads(payload)
    except json.JSONDecodeError as e:
        return {"valid": False, "reason": f"signature valid but payload isn't valid JSON: {e}", "statement": None}

    return {"valid": True, "reason": "signature valid", "statement": statement}
