# Watcher Suite

Local-first change logging for git repos with AI summaries and a lightweight FastAPI dashboard.

## What it does
- Polls your repo for uncommitted changes every 30s.
- Logs diffs with branch, files, timestamp, and an OpenAI summary to JSONL under `changelog/`.
- Serves a web UI to browse change history, view diffs, see recent commits, safely create review branches, and compare namespaces (functions/classes/tables/columns) between refs.

## Files
- `watcher.py` — background poller/logger (run from repo root).
- `openai_client.py` — OpenAI summarizer with retries.
- `server/` — FastAPI app, git helpers, namespace indexer, and dashboard UI.
- `watcher-overview.html` — one-page product overview.
- `.gitignore` — excludes venv/pyc/env/changelog.

## Requirements
- Python 3.9+
- `pip install fastapi uvicorn openai jinja2` (and `python-dotenv` if you use a `.env` file)
- Git available on PATH
- `OPENAI_API_KEY` in your environment (optional: `WATCHER_MODEL`, defaults to `gpt-4o-mini`)

## Run the watcher
From the repo you want to monitor:
```bash
python watcher.py
```
- Poll interval: 30 seconds.
- Logs to `changelog/YYYY-MM-DD.jsonl` (auto-created).
- Never stages/commits; read-only git commands only.

## Run the dashboard
From the same repo:
```bash
uvicorn server.app:app --reload --port 5050
```
Open http://localhost:5050 (or VS Code Simple Browser).

### Dashboard features
- Change Timeline: filter by date/branch/file; click to view summary + raw diff.
- Git Panel: recent commits, per-commit diff, status, checkout to new `review/<hash>` branch (requires clean worktree).
- Namespace Diff: compares two refs (default WORKTREE vs HEAD) for functions/classes/methods/tables/columns with file and type filters; flags likely renames (case/underscore changes).

## Config knobs
- `POLL_INTERVAL_SECONDS` in `watcher.py` (default 30).
- `WATCHER_MODEL` env var to pick an OpenAI model.
- OpenAI request settings are in `openai_client.py` (temperature/max tokens/retries).

## Log format (JSON Lines)
Each line in `changelog/YYYY-MM-DD.jsonl`:
```json
{
  "timestamp": "2025-11-23T12:34:56.789Z",
  "branch": "main",
  "files": ["src/app.py", "README.md"],
  "diff": "...unified diff...",
  "summary": "Short AI summary"
}
```

## Safety
- Watcher uses only `git status`, `git diff`, `git rev-parse`.
- Dashboard checkout path: clean worktree required, creates a new branch; never resets HEAD.

## Reuse in other projects
- Copy this folder into any repo.
- Ensure deps and `OPENAI_API_KEY` are set.
- Run watcher + dashboard from that repo root.
