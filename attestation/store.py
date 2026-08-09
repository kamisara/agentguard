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
