"""
Git commit-time capture - Tier 5, the universal fallback.

Day 1 deliberately skips a BaseAdapter class. This is a standalone function
so we can validate the CaptureEvent shape and the normalizer against REAL
commit data before locking in an adapter interface based on guesses.

IMPORTANT: git has no concept of "developer intent" or "AI response". We are
INFERRING intent from the commit message and treating the diff as the
artifact. This is why IntentSource exists in NormalizedEvent - do not let
this get silently conflated with an explicitly captured prompt.
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Union

from .types import CaptureEvent

# Git's well-known empty-tree hash. Used as the diff base for a repo's first
# commit, which has no parent to diff against (HEAD~1 fails there).
EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# Unit separator - safe against commit message content, unlike newlines,
# which frequently appear in multi-line commit bodies.
FIELD_SEP = "\x1f"


def _run(cmd: list, cwd: Union[str, Path]) -> str:
    result = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _get_last_commit(repo_path: Union[str, Path]) -> dict:
    """Parses `git log -1` output using a delimiter instead of naive newline
    splitting, since commit bodies are frequently multi-line."""
    fmt = FIELD_SEP.join(["%H", "%an", "%ae", "%aI", "%s", "%b"])
    raw = _run(["git", "log", "-1", f"--format={fmt}"], repo_path)
    parts = raw.split(FIELD_SEP)
    commit_hash, author_name, author_email, date, subject = parts[:5]
    # body can legitimately contain the separator if it was in the original
    # message; rejoin defensively
    body = FIELD_SEP.join(parts[5:]).strip()

    return {
        "hash": commit_hash,
        "author_name": author_name,
        "author_email": author_email,
        "date": date,
        "subject": subject,
        "body": body,
    }


def _get_diff_stat(repo_path: Union[str, Path]) -> dict:
    """Handles the edge case that breaks naive implementations: the very
    first commit in a repo has no parent, so `HEAD~1` fails."""
    try:
        raw = _run(
            ["git", "diff", "HEAD~1", "HEAD", "--shortstat"], repo_path
        )
    except subprocess.CalledProcessError:
        # first commit, or detached/unborn HEAD - diff against the empty tree
        raw = _run(
            ["git", "diff", EMPTY_TREE_HASH, "HEAD", "--shortstat"], repo_path
        )

    if not raw:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "raw": ""}

    files_match = re.search(r"(\d+) files? changed", raw)
    ins_match = re.search(r"(\d+) insertions?\(\+\)", raw)
    del_match = re.search(r"(\d+) deletions?\(-\)", raw)

    return {
        "files_changed": int(files_match.group(1)) if files_match else 0,
        "insertions": int(ins_match.group(1)) if ins_match else 0,
        "deletions": int(del_match.group(1)) if del_match else 0,
        "raw": raw,
    }


def capture_from_git(repo_path: Union[str, Path, None] = None) -> CaptureEvent:
    """Captures the most recent commit as a CaptureEvent.

    Field mapping decisions (these are exactly the assumptions we wanted
    real data to validate before locking into a schema):
      - prompt    -> commit subject + body (this IS the inferred intent)
      - response  -> a summary of the diff, NOT the full diff (full diffs
                     belong in metadata["diff_stat"]["raw"], not the response
                     field - keeps the schema consistent with adapters where
                     "response" is model output text, not a code blob)
      - developer -> commit author
      - session_id -> left None; git has no session concept
      - model     -> left None; git has no model concept.
                     Future improvement: detect AI attribution trailers
                     (e.g. "Co-authored-by: Claude") and populate this.
    """
    repo_path = repo_path or Path.cwd()
    commit = _get_last_commit(repo_path)
    diff_stat = _get_diff_stat(repo_path)

    intent_text = (
        f"{commit['subject']}\n\n{commit['body']}"
        if commit["body"]
        else commit["subject"]
    )

    return CaptureEvent(
        adapter="git",
        timestamp=datetime.fromisoformat(commit["date"]),
        prompt=intent_text,
        response=(
            f"{diff_stat['files_changed']} file(s) changed, "
            f"+{diff_stat['insertions']}/-{diff_stat['deletions']}"
        ),
        developer=f"{commit['author_name']} <{commit['author_email']}>",
        metadata={
            "commit_hash": commit["hash"],
            "diff_stat": diff_stat["raw"],
        },
    )
