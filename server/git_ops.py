"""
Thin wrappers around git commands for the dashboard.
All operations are read-only except checkout_commit, which creates a new branch.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


def _run(args: List[str]) -> str:
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(args)}")
    return result.stdout.strip()


@dataclass
class CommitEntry:
    hash: str
    short_hash: str
    title: str


def list_commits(limit: int = 50) -> List[CommitEntry]:
    output = _run(["git", "log", "--oneline", f"-n{limit}"])
    commits: List[CommitEntry] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        commit_hash = parts[0]
        title = parts[1] if len(parts) > 1 else ""
        commits.append(CommitEntry(hash=commit_hash, short_hash=commit_hash[:7], title=title))
    return commits


def show_diff(commit_hash: str) -> str:
    return _run(["git", "show", commit_hash])


def status() -> str:
    return _run(["git", "status", "--short", "--branch"])


def ensure_clean_worktree() -> None:
    output = _run(["git", "status", "--porcelain"])
    if output.strip():
        raise RuntimeError("Working tree is not clean; aborting checkout.")


def checkout_commit(commit_hash: str, branch_name: str | None = None) -> str:
    """
    Create a new branch at the given commit. Fails if worktree dirty or branch exists.
    """
    ensure_clean_worktree()
    target_branch = branch_name or f"review/{commit_hash[:7]}"
    # Check if branch already exists
    try:
        _run(["git", "show-ref", "--verify", f"refs/heads/{target_branch}"])
        raise RuntimeError(f"Branch '{target_branch}' already exists.")
    except RuntimeError:
        # show-ref exits non-zero if not found; we treat that as okay
        pass
    _run(["git", "checkout", "-b", target_branch, commit_hash])
    return target_branch
