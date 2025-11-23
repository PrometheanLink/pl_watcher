"""
Namespace indexer for Python code: extracts functions, classes, methods, and ORM table/field names.
Supports scanning the worktree or a git ref (via `git show`).
"""
from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class FileNamespace:
    functions: Set[str] = field(default_factory=set)
    classes: Set[str] = field(default_factory=set)
    methods: Set[str] = field(default_factory=set)
    tables: Set[str] = field(default_factory=set)
    columns: Set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "functions": sorted(self.functions),
            "classes": sorted(self.classes),
            "methods": sorted(self.methods),
            "tables": sorted(self.tables),
            "columns": sorted(self.columns),
        }


def _run_git_show(ref: str, path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=BASE_DIR,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def _iter_python_files_worktree(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        # Skip virtual environments or hidden dirs
        if any(part.startswith(".") for part in path.parts):
            continue
        if "venv" in path.parts or "env" in path.parts or "node_modules" in path.parts:
            continue
        yield path


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.ns = FileNamespace()
        self._class_name: Optional[str] = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if self._class_name:
            self.ns.methods.add(f"{self._class_name}.{node.name}")
        else:
            self.ns.functions.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        # Treat async like normal for naming
        if self._class_name:
            self.ns.methods.add(f"{self._class_name}.{node.name}")
        else:
            self.ns.functions.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.ns.classes.add(node.name)
        prev = self._class_name
        self._class_name = node.name
        # Detect __tablename__ and column-like assignments
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "__tablename__" and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                            self.ns.tables.add(stmt.value.value)
                        elif target.id != "__tablename__":
                            # crude heuristic: capture attribute names as potential columns/fields
                            self.ns.columns.add(target.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    self.ns.columns.add(stmt.target.id)
        # Visit methods
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(stmt)
        self._class_name = prev


def _parse_source(src: str) -> FileNamespace:
    visitor = _Visitor()
    try:
        tree = ast.parse(src)
        visitor.visit(tree)
    except SyntaxError:
        pass
    return visitor.ns


def scan_worktree(root: Path = BASE_DIR) -> Dict[str, FileNamespace]:
    result: Dict[str, FileNamespace] = {}
    for path in _iter_python_files_worktree(root):
        try:
            src = path.read_text(encoding="utf-8")
        except Exception:
            continue
        ns = _parse_source(src)
        relative = str(path.relative_to(root))
        result[relative] = ns
    return result


def scan_ref(ref: str, root: Path = BASE_DIR) -> Dict[str, FileNamespace]:
    """
    Scan Python files at a git ref without checking it out. Uses `git ls-tree` to list files.
    """
    result: Dict[str, FileNamespace] = {}
    try:
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=root,
        )
        if listing.returncode != 0:
            return result
    except Exception:
        return result

    for line in listing.stdout.splitlines():
        if not line.endswith(".py"):
            continue
        src = _run_git_show(ref, line)
        if src is None:
            continue
        ns = _parse_source(src)
        result[line] = ns
    return result


def diff_namespaces(a: Dict[str, FileNamespace], b: Dict[str, FileNamespace]) -> dict:
    """
    Compute added/removed identifiers between two namespace snapshots.
    """
    def norm(name: str) -> str:
        return name.replace("_", "").replace("-", "").lower()

    files = set(a.keys()) | set(b.keys())
    file_diffs = {}
    added_total = {"functions": set(), "classes": set(), "methods": set(), "tables": set(), "columns": set()}
    removed_total = {"functions": set(), "classes": set(), "methods": set(), "tables": set(), "columns": set()}
    rename_candidates = []

    for f in sorted(files):
        na = a.get(f, FileNamespace())
        nb = b.get(f, FileNamespace())
        file_diff = {}
        for key in ["functions", "classes", "methods", "tables", "columns"]:
            set_a = getattr(na, key)
            set_b = getattr(nb, key)
            added = set_b - set_a
            removed = set_a - set_b
            # Detect simple renames (case/underscore changes) between removed/added
            norm_added = {norm(s): s for s in added}
            for r in removed:
                n = norm(r)
                if n in norm_added and norm_added[n] != r:
                    rename_candidates.append({
                        "file": f,
                        "type": key,
                        "from": r,
                        "to": norm_added[n],
                    })
            if added or removed:
                file_diff[key] = {
                    "added": sorted(added),
                    "removed": sorted(removed),
                }
                added_total[key].update(added)
                removed_total[key].update(removed)
        if file_diff:
            file_diffs[f] = file_diff

    return {
        "files": file_diffs,
        "added_totals": {k: sorted(v) for k, v in added_total.items()},
        "removed_totals": {k: sorted(v) for k, v in removed_total.items()},
        "renames": rename_candidates,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Namespace indexer")
    parser.add_argument("--ref-a", default="WORKTREE", help="First ref (default worktree)")
    parser.add_argument("--ref-b", default="HEAD", help="Second ref (default HEAD)")
    args = parser.parse_args()

    a = scan_worktree() if args.ref_a.upper() == "WORKTREE" else scan_ref(args.ref_a)
    b = scan_worktree() if args.ref_b.upper() == "WORKTREE" else scan_ref(args.ref_b)
    print(json.dumps(diff_namespaces(a, b), indent=2))
