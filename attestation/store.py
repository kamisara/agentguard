"""
Writes/reads ContextualAttestation records to/from .agentguard/attestations/
- same directory convention agentguard.py's original capture() command
already used, so old (sprint1-v0) and new (sprint3-v1) records live
side by side and both work with list_attestations()/show().
"""

import json
from pathlib import Path
from typing import List, Optional, Union

from .types import ContextualAttestation

ATTESTATION_DIR_NAME = Path(".agentguard") / "attestations"


def _attestation_dir(repo_path: Union[str, Path, None] = None) -> Path:
    base = Path(repo_path) if repo_path else Path.cwd()
    d = base / ATTESTATION_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_attestation(
    attestation: ContextualAttestation, repo_path: Union[str, Path, None] = None
) -> Path:
    out_dir = _attestation_dir(repo_path)
    out_path = out_dir / f"{attestation.attestation_id}.json"
    out_path.write_text(json.dumps(attestation.to_dict(), indent=2, default=str))
    return out_path


def write_and_sign_attestation(
    attestation: ContextualAttestation, repo_path: Union[str, Path, None] = None
) -> tuple:
    """Writes the attestation, then signs it - two files, the plain JSON
    (unchanged shape, still readable by anything reading unsigned records)
    plus a detached .sig file. Signing is intentionally a separate step
    from writing, not baked into write_attestation() - matches the
    proposal's own architecture table, which lists "Contextual Attestation
    generation" and "Cosign signing" as distinct sub-steps of the
    Attestation layer, and keeps write_attestation() usable standalone for
    anything that doesn't need/want signing (e.g. quick local testing).

    Returns (attestation_path, signature_path)."""
    from signing.keys import get_or_create_keypair
    from signing.signer import write_signature

    attestation_path = write_attestation(attestation, repo_path)
    private_key_path, public_key_path = get_or_create_keypair(repo_path)
    sig_path = write_signature(
        attestation_path, attestation.to_dict(), private_key_path, public_key_path
    )
    return attestation_path, sig_path


def list_attestation_files(repo_path: Union[str, Path, None] = None) -> List[Path]:
    return sorted(_attestation_dir(repo_path).glob("*.json"))


def read_attestation_dict(path: Path) -> Optional[dict]:
    """Returns the raw dict, not a ContextualAttestation instance -
    intentional, since sprint1-v0 records don't match the dataclass
    fields and both schemas need to be readable by agentguard.py's
    list/show commands without one schema crashing on the other."""
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
