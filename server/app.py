"""
FastAPI server exposing change logs and basic git controls.

Run from the repo root (or ensure cwd is a git repo):
    uvicorn server.app:app --reload --port 5050
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import changelog_reader
from . import git_ops
from . import namespace_indexer


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Watcher Dashboard", version="0.1.0")

# Serve root template
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/changes")
async def list_changes(
    date: Optional[str] = None,
    branch: Optional[str] = None,
    file: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    entries = changelog_reader.load_entries()
    filtered = changelog_reader.filter_entries(entries, date=date, branch=branch, file_substring=file)
    total = len(filtered)
    paged = filtered[offset : offset + limit]
    return {"items": [e.__dict__ for e in paged], "total": total}


@app.get("/api/changes/{entry_id}")
async def change_detail(entry_id: str):
    entry = changelog_reader.get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Change not found")
    return entry.__dict__


@app.get("/api/commits")
async def commits(limit: int = 50):
    return {"items": [c.__dict__ for c in git_ops.list_commits(limit=limit)]}


@app.get("/api/commits/{commit_hash}")
async def commit_detail(commit_hash: str):
    try:
        diff = git_ops.show_diff(commit_hash)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"hash": commit_hash, "diff": diff}


@app.get("/api/status")
async def git_status():
    try:
        status_text = git_ops.status()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": status_text}


@app.post("/api/checkout")
async def checkout(body: dict):
    commit_hash = body.get("hash")
    branch_name = body.get("branch")
    if not commit_hash:
        raise HTTPException(status_code=400, detail="hash is required")
    try:
        new_branch = git_ops.checkout_commit(commit_hash, branch_name=branch_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"branch": new_branch}


@app.get("/api/namespaces")
async def namespaces(ref: str = "WORKTREE"):
    try:
        snapshot = namespace_indexer.scan_worktree() if ref.upper() == "WORKTREE" else namespace_indexer.scan_ref(ref)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {path: ns.to_dict() for path, ns in snapshot.items()}


@app.get("/api/namespaces/diff")
async def namespaces_diff(ref_a: str = "WORKTREE", ref_b: str = "HEAD"):
    try:
        a = namespace_indexer.scan_worktree() if ref_a.upper() == "WORKTREE" else namespace_indexer.scan_ref(ref_a)
        b = namespace_indexer.scan_worktree() if ref_b.upper() == "WORKTREE" else namespace_indexer.scan_ref(ref_b)
        diff = namespace_indexer.diff_namespaces(a, b)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return diff
