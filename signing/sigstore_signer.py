"""
Sigstore keyless signing - the second signing method, per the proposal's
"Sigstore/Cosign, with support for self-hosted key infrastructure" line.
signer.py (Ed25519, local keypair) implements the self-hosted half;
this implements the keyless half.

HONESTLY STATED LIMITATION, found via direct testing, not assumed: this
module's real network calls (to Fulcio, the certificate authority) could
NOT be executed in the sandbox this was developed in - confirmed via a
direct connection attempt, which returned HTTP 403 (blocked by network
policy), not a DNS/timeout failure. This is a genuinely common situation,
not just a quirk of one sandbox - restricted corporate networks and many
CI environments block egress to third-party signing infrastructure the
same way. The code below is built against the REAL installed sigstore
Python package's actual API (confirmed via runtime inspection of the
installed version - `sigstore==4.5.0` at the time this was written, since
this library's public API has changed across versions and guessing from
memory would risk the exact kind of wrong-assumption bug this project has
hit and fixed before with Copilot's transcript format and OTel message
shape). It has NOT been exercised end-to-end against real Fulcio/Rekor
infrastructure. That requires:
  1. A real OIDC login (interactive browser flow - Issuer.identity_token()
     blocks and opens a browser; there is no way to do this headlessly).
  2. Network access to Sigstore's public production infrastructure
     (fulcio.sigstore.dev, rekor.sigstore.dev, oauth2.sigstore.dev).
Both are available on a normal developer machine, just not in this
sandbox. See test_sigstore_keyless.py for what WAS actually verified here
(import correctness, graceful failure when the network is blocked) versus
what still needs a real machine to confirm.

What keyless signing adds over signer.py's local-key approach: identity
binding (the signature is tied to a real OIDC identity - a GitHub/Google
account - via a short-lived Fulcio-issued certificate) and public
auditability (logged to Rekor, a public transparency log anyone can
check). signer.py's local keypair only proves "whoever holds this
private key signed this" - no external identity, no public log.
"""

from pathlib import Path
from typing import Union

from sigstore.sign import SigningContext
from sigstore.models import Bundle, ClientTrustConfig
from sigstore.oidc import Issuer, IdentityToken
from sigstore.verify import Verifier
from sigstore.verify.policy import Identity

# Sigstore's public production OIDC issuer. Confirmed from sigstore-python's
# own CLI source (sigstore/_cli.py) rather than guessed.
PRODUCTION_OIDC_ISSUER_URL = "https://oauth2.sigstore.dev/auth"


def get_identity_token() -> IdentityToken:
    """Triggers an interactive browser-based OIDC login. Blocks until the
    user completes it. This is the step that cannot be automated or run
    headlessly - by design, since the whole point of keyless signing is
    binding the signature to a real, interactively-verified identity."""
    issuer = Issuer(PRODUCTION_OIDC_ISSUER_URL)
    return issuer.identity_token()


def sign_keyless(artifact_bytes: bytes, identity_token: IdentityToken = None) -> Bundle:
    """Signs artifact_bytes, returning a Bundle (Sigstore's standard
    signing-material container - certificate, signature, Rekor inclusion
    proof). identity_token can be supplied by the caller to avoid
    triggering a fresh browser login for every signature in a session -
    if omitted, get_identity_token() is called, which WILL open a
    browser."""
    if identity_token is None:
        identity_token = get_identity_token()

    trust_config = ClientTrustConfig.production()
    signing_ctx = SigningContext.from_trust_config(trust_config)
    with signing_ctx.signer(identity_token) as signer:
        return signer.sign_artifact(input_=artifact_bytes)


def verify_keyless(
    artifact_bytes: bytes, bundle: Bundle, expected_identity: str, expected_issuer: str = None
) -> dict:
    """Verifies a Bundle against the artifact AND checks the signing
    identity matches expected_identity (e.g. "someone@example.com") and,
    if given, expected_issuer (e.g. "https://accounts.google.com").
    Checking identity is not optional here the way key-based verification
    only checks "does this key match" - keyless verification without an
    identity check would accept a signature from ANYONE with a valid
    Sigstore-issued certificate, not just the expected signer."""
    verifier = Verifier.production()
    policy = Identity(identity=expected_identity, issuer=expected_issuer)
    try:
        verifier.verify_artifact(input_=artifact_bytes, bundle=bundle, policy=policy)
        return {"valid": True, "reason": "signature and identity verified"}
    except Exception as e:
        return {"valid": False, "reason": f"{type(e).__name__}: {e}"}


def bundle_path_for(attestation_path: Union[str, Path]) -> Path:
    """Sigstore's own convention is a `.sigstore.json` sibling file -
    matched here rather than inventing a different extension, so output
    from this tool is recognizable to anyone familiar with the standard
    Sigstore/cosign tooling."""
    attestation_path = Path(attestation_path)
    return attestation_path.with_suffix("").with_suffix(".sigstore.json")


def sign_attestation_file_keyless(
    attestation_path: Union[str, Path], identity_token: IdentityToken = None
) -> Path:
    attestation_path = Path(attestation_path)
    artifact_bytes = attestation_path.read_bytes()
    bundle = sign_keyless(artifact_bytes, identity_token)

    out_path = bundle_path_for(attestation_path)
    out_path.write_text(bundle.to_json())
    return out_path


def verify_attestation_file_keyless(
    attestation_path: Union[str, Path], expected_identity: str, expected_issuer: str = None
) -> dict:
    attestation_path = Path(attestation_path)
    bundle_path = bundle_path_for(attestation_path)

    if not attestation_path.exists():
        return {"valid": False, "reason": "attestation file not found"}
    if not bundle_path.exists():
        return {"valid": False, "reason": "no .sigstore.json bundle found (not keyless-signed)"}

    artifact_bytes = attestation_path.read_bytes()
    bundle = Bundle.from_json(bundle_path.read_text())
    return verify_keyless(artifact_bytes, bundle, expected_identity, expected_issuer)
