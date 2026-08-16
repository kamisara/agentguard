"""
Key management for Sprint 4 signing - self-hosted key infrastructure,
per the proposal's explicit alternative to Sigstore's keyless flow.

SCOPE, stated honestly: this is real asymmetric-key cryptography (Ed25519
via the `cryptography` package - the same primitive Sigstore itself uses
under the hood for leaf certificates), not a placeholder. What's NOT
implemented: Sigstore's keyless signing (Fulcio-issued short-lived certs
tied to an OIDC identity, logged to the public Rekor transparency log).
That path needs a browser-based OIDC login and network calls to public
Sigstore infrastructure - unsuitable for automated local testing the way
everything else in this project has been tested. It's a real, documented
future extension (see README), not silently skipped.

Keys are stored PEM-encoded in .agentguard/keys/ - generated on first use
if not present. This is a LOCAL trust root: verification only proves "the
holder of this private key signed this", not "a specific, externally
verifiable identity signed this" (that's what Fulcio would add). Stated
plainly because it's the actual security property being provided, not an
inflated claim.
"""

from pathlib import Path
from typing import Tuple, Union

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

KEY_DIR_NAME = Path(".agentguard") / "keys"
PRIVATE_KEY_FILENAME = "agentguard_private.pem"
PUBLIC_KEY_FILENAME = "agentguard_public.pem"


def _key_dir(repo_path: Union[str, Path, None] = None) -> Path:
    base = Path(repo_path) if repo_path else Path.cwd()
    d = base / KEY_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_keypair(repo_path: Union[str, Path, None] = None) -> Tuple[Path, Path]:
    """Generates a new Ed25519 keypair and writes both PEM files. Does NOT
    check for an existing keypair first - callers should use
    get_or_create_keypair() for the common "use existing or make one"
    case. Overwrites any existing keys at the same path - this is
    deliberately explicit/dangerous, not the default path, so nobody
    silently invalidates every existing signature by accident."""
    key_dir = _key_dir(repo_path)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_path = key_dir / PRIVATE_KEY_FILENAME
    public_path = key_dir / PUBLIC_KEY_FILENAME

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def get_or_create_keypair(repo_path: Union[str, Path, None] = None) -> Tuple[Path, Path]:
    key_dir = _key_dir(repo_path)
    private_path = key_dir / PRIVATE_KEY_FILENAME
    public_path = key_dir / PUBLIC_KEY_FILENAME

    if private_path.exists() and public_path.exists():
        return private_path, public_path
    return generate_keypair(repo_path)


def load_private_key(path: Union[str, Path]) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(Path(path).read_bytes(), password=None)


def load_public_key(path: Union[str, Path]) -> Ed25519PublicKey:
    return serialization.load_pem_public_key(Path(path).read_bytes())
