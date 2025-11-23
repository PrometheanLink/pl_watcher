"""
Background watcher that logs uncommitted git changes with OpenAI summaries.

Usage: run from the root of a git repository:
    python watcher.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from openai_client import summarize_diff


POLL_INTERVAL_SECONDS = 30
CHANGELOG_DIR = Path("changelog")


def run_cmd(args: List[str]) -> str:
    """Run a shell command and return stdout; raise on failure."""
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def get_status_lines() -> List[str]:
    """Return lines from `git status --porcelain`."""
    output = run_cmd(["git", "status", "--porcelain"])
    return [line for line in output.splitlines() if line.strip()]


def get_changed_files(status_lines: List[str]) -> List[str]:
    """Extract file paths from porcelain status lines."""
    files = []
    for line in status_lines:
        # Format: XY <path> (possibly ' -> ' for renames)
        path_part = line[3:] if len(line) > 3 else line
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[-1]
        if path_part:
            files.append(path_part)
    return sorted(set(files))


def get_diff() -> str:
    """Return the unified diff of unstaged + staged changes."""
    return run_cmd(["git", "diff"])


def get_branch() -> str:
    """Return the current branch name."""
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])


def append_log(entry: dict) -> None:
    """Append a JSON log line to today's changelog file."""
    CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
    path = CHANGELOG_DIR / filename
    with path.open("a", encoding="utf-8") as f:
        json.dump(entry, f)
        f.write("\n")


def build_entry(status_lines: List[str]) -> dict:
    """Build the log entry with timestamp, branch, files, diff, and summary."""
    diff_text = get_diff()
    summary = summarize_diff(diff_text)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": get_branch(),
        "files": get_changed_files(status_lines),
        "diff": diff_text,
        "summary": summary,
    }
    return entry


def main() -> None:
    print("Watcher started. Polling every", POLL_INTERVAL_SECONDS, "seconds.")
    while True:
        try:
            status_lines = get_status_lines()
            if status_lines:
                entry = build_entry(status_lines)
                append_log(entry)
                print(f"[{entry['timestamp']}] Logged changes on branch {entry['branch']} "
                      f"({len(entry['files'])} files).")
            time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nWatcher stopped by user.")
            break
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Ensure we are inside a git repo
    try:
        run_cmd(["git", "rev-parse", "--is-inside-work-tree"])
    except Exception as exc:  # pragma: no cover - startup guard
        print(f"Not inside a git repository: {exc}", file=sys.stderr)
        sys.exit(1)

    main()
