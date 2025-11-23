"""
Utilities to read and filter changelog JSONL files produced by watcher.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

CHANGELOG_DIR = Path(__file__).resolve().parent.parent / "changelog"


@dataclass
class ChangeEntry:
    id: str
    timestamp: str
    branch: str
    files: List[str]
    summary: str
    date: str
    diff_present: bool


@dataclass
class ChangeDetail(ChangeEntry):
    diff: str


def _iter_jsonl_files() -> Iterable[Path]:
    if not CHANGELOG_DIR.exists():
        return []
    return sorted(CHANGELOG_DIR.glob("*.jsonl"))


def _parse_file(path: Path) -> Iterable[ChangeDetail]:
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = data.get("timestamp", "")
            date = ""
            try:
                date = timestamp.split("T", 1)[0]
            except Exception:
                pass
            entry_id = f"{path.stem}#{idx}"
            files = data.get("files") or []
            if isinstance(files, str):
                files = [files]
            diff = data.get("diff", "")
            summary = data.get("summary", "")
            yield ChangeDetail(
                id=entry_id,
                timestamp=timestamp,
                branch=data.get("branch", ""),
                files=files,
                summary=summary,
                date=date,
                diff_present=bool(diff),
                diff=diff,
            )


def load_entries() -> List[ChangeDetail]:
    """Load all changelog entries from JSONL files."""
    entries: List[ChangeDetail] = []
    for path in _iter_jsonl_files():
        entries.extend(_parse_file(path))
    # Sort newest first by timestamp fallback to id
    entries.sort(key=lambda e: e.timestamp or e.id, reverse=True)
    return entries


def filter_entries(
    entries: Iterable[ChangeDetail],
    date: Optional[str] = None,
    branch: Optional[str] = None,
    file_substring: Optional[str] = None,
) -> List[ChangeEntry]:
    """Filter entries and return timeline-friendly ChangeEntry objects."""
    results: List[ChangeEntry] = []
    file_substring_lower = file_substring.lower() if file_substring else None
    for entry in entries:
        if date and entry.date != date:
            continue
        if branch and entry.branch != branch:
            continue
        if file_substring_lower:
            if not any(file_substring_lower in f.lower() for f in entry.files):
                continue
        results.append(
            ChangeEntry(
                id=entry.id,
                timestamp=entry.timestamp,
                branch=entry.branch,
                files=entry.files,
                summary=entry.summary,
                date=entry.date,
                diff_present=entry.diff_present,
            )
        )
    return results


def get_entry_by_id(entry_id: str) -> Optional[ChangeDetail]:
    """Lookup an entry by its id (date#lineno)."""
    try:
        date_part = entry_id.split("#", 1)[0]
    except Exception:
        date_part = None

    candidates = [p for p in _iter_jsonl_files() if p.stem == date_part] if date_part else _iter_jsonl_files()
    for path in candidates:
        for entry in _parse_file(path):
            if entry.id == entry_id:
                return entry
    return None
