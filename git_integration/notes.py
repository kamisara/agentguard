"""
Sprint 5, Day 1: Git Integration.

Attaches attestation references to the specific git commit they relate
to, using `git notes` - a real, standard git mechanism for attaching
arbitrary metadata to a commit WITHOUT altering the commit hash (unlike
amending the commit message, which would rewrite history and break every
child commit's hash). This is what makes an attestation discoverable as
a first-class part of the commit's provenance record, per the proposal's
"Integration with existing in-toto layouts so that AI generation steps
appear as first-class links in the software supply chain" goal.

Uses a dedicated notes ref (refs/notes/agentguard) rather than git's
default notes ref (refs/notes/commits), so this doesn't collide with any
other tool or workflow that might already use plain `git notes`.

One commit can have MULTIPLE attestations (e.g. several AI-assisted edits
before a single commit) - `git notes append` is used, not `git notes add`
(which would overwrite), and each attestation reference is stored as one
JSON line so multiple entries stay parseable rather than colliding into
unstructured text.

SPRINT 6 SELF-CONTAINMENT FIX, found via real live CI testing (2026-09):
the original design stored only {"attestation_id", "attestation_path"} -
a reference to an external file - in the note. This broke in practice for
reasons that only showed up on a real GitHub Actions run, not in local
testing:

  1. .agentguard/ is commonly gitignored (local/ephemeral state), so the
     referenced attestation file was never actually pushed to the
     remote - the note existed, but pointed at nothing CI could see.
  2. Even if force-committed, the attestation file for commit N typically
     gets added in a LATER commit N+1 (you attest N, then commit the
     attestation file itself) - but CI checks whatever commit actually
     triggered it (often N+1), which has no note of its own. The note is
     correctly on N; the file ends up needing to exist in N+1's tree;
     the two never line up cleanly under a single-commit gate check.

Both problems disappear if the note is fully SELF-CONTAINED: the full
attestation dict, its signature, and the public key needed to verify it,
all embedded directly in the note text. Once `git fetch refs/notes/*`
has run, verification needs nothing else from the checkout at all - no
external file, no gitignore interaction, no commit-ordering dependency.
"""

import json
import subprocess
from pathlib import Path
from typing import List, Optional, Union

NOTES_REF = "refs/notes/agentguard"


def _run_git(args: list, repo_path: Union[str, Path, None] = None) -> str:
    repo_path = repo_path or Path.cwd()
    result = subprocess.run(
        ["git"] + args,
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def attach_attestation_note(
    commit_hash: str,
    attestation_dict: dict,
    signature_b64: str,
    public_key_pem: str,
    repo_path: Union[str, Path, None] = None,
) -> None:
    """Appends a FULLY SELF-CONTAINED attestation record onto the given
    commit's agentguard note - the attestation content, its signature,
    and the public key to verify it, all embedded directly. No external
    file dependency at read time. Idempotent in intent (appending the
    same reference twice would duplicate it - callers should check
    get_attestations_for_commit() first if that matters for their use
    case; not enforced here since "attach again" is a legitimate action
    if genuinely re-signing or re-attesting the same commit)."""
    note_line = json.dumps({
        "attestation_id": attestation_dict.get("attestation_id"),
        "attestation": attestation_dict,
        "signature": signature_b64,
        "public_key_pem": public_key_pem,
    })
    _run_git(
        ["notes", f"--ref={NOTES_REF}", "append", "-m", note_line, commit_hash],
        repo_path,
    )


def get_attestations_for_commit(
    commit_hash: str, repo_path: Union[str, Path, None] = None
) -> List[dict]:
    """Returns the list of self-contained entries
    ({attestation_id, attestation, signature, public_key_pem}) attached
    to this commit. Returns [] if the commit has no agentguard note at
    all - this is the normal case for any commit not made through
    AgentGuard's capture flow, not an error."""
    try:
        raw = _run_git(
            ["notes", f"--ref={NOTES_REF}", "show", commit_hash], repo_path
        )
    except RuntimeError:
        return []  # no note on this commit - normal, not an error

    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip a malformed line rather than fail the whole lookup
    return entries


def get_current_commit_hash(repo_path: Union[str, Path, None] = None) -> Optional[str]:
    try:
        return _run_git(["rev-parse", "HEAD"], repo_path)
    except RuntimeError:
        return None
