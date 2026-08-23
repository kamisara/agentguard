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
    attestation_id: str,
    attestation_path: Union[str, Path],
    repo_path: Union[str, Path, None] = None,
) -> None:
    """Appends a reference to this attestation onto the given commit's
    agentguard note. Idempotent in intent (appending the same reference
    twice would duplicate it - callers should check
    get_attestations_for_commit() first if that matters for their use
    case; not enforced here since "attach again" is a legitimate action
    if genuinely re-signing or re-attesting the same commit)."""
    note_line = json.dumps({
        "attestation_id": attestation_id,
        "attestation_path": str(attestation_path),
    })
    _run_git(
        ["notes", f"--ref={NOTES_REF}", "append", "-m", note_line, commit_hash],
        repo_path,
    )


def get_attestations_for_commit(
    commit_hash: str, repo_path: Union[str, Path, None] = None
) -> List[dict]:
    """Returns the list of {attestation_id, attestation_path} dicts
    attached to this commit. Returns [] if the commit has no agentguard
    note at all - this is the normal case for any commit not made
    through AgentGuard's capture flow, not an error."""
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
