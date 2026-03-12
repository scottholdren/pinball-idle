#!/usr/bin/env python3
"""
Git post-commit hook.
Finds Claude Code session temp files written in the last 30 minutes,
merges them with the current commit data, appends to .claude-audit/log.json,
stages the log file, and amends the commit to include it.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


AUDIT_LOG = Path(".claude-audit/log.json")
TMP_DIR = Path("/tmp")
SESSION_GLOB = "claude-audit-*.json"
SESSION_MAX_AGE_MINUTES = 30


def run(cmd: list[str], check=True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def get_commit_data() -> dict:
    commit_hash = run(["git", "rev-parse", "HEAD"])
    commit_msg = run(["git", "log", "-1", "--pretty=%s"])
    files_changed = run(["git", "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD"])
    author = run(["git", "log", "-1", "--pretty=%an"])
    timestamp = run(["git", "log", "-1", "--pretty=%aI"])

    return {
        "commit": commit_hash,
        "timestamp": timestamp,
        "message": commit_msg,
        "author": author,
        "files_changed": [f for f in files_changed.splitlines() if f],
    }


def find_recent_sessions() -> list[Path]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_MAX_AGE_MINUTES)
    sessions = []

    for tmp_file in TMP_DIR.glob(SESSION_GLOB):
        mtime = datetime.fromtimestamp(tmp_file.stat().st_mtime, tz=timezone.utc)
        if mtime >= cutoff:
            sessions.append(tmp_file)

    return sessions


def consume_session(tmp_file: Path) -> dict | None:
    try:
        data = json.loads(tmp_file.read_text())
        # rename to .done so it can't be consumed twice
        done_path = tmp_file.with_suffix(".done")
        tmp_file.rename(done_path)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def load_log() -> list:
    if not AUDIT_LOG.exists():
        return []
    try:
        return json.loads(AUDIT_LOG.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_log(entries: list):
    AUDIT_LOG.parent.mkdir(exist_ok=True)
    AUDIT_LOG.write_text(json.dumps(entries, indent=2))


def main():
    sessions = find_recent_sessions()

    if not sessions:
        # no claude session found - commit proceeds normally, no audit entry
        sys.exit(0)

    commit_data = get_commit_data()

    # skip if this is the audit log amend commit itself (avoid infinite loop)
    if commit_data["files_changed"] == [str(AUDIT_LOG)]:
        sys.exit(0)

    entries = load_log()

    for tmp_file in sessions:
        session = consume_session(tmp_file)
        if not session:
            continue

        entry = {
            **commit_data,
            "claude": {
                "session_id": session["session_id"],
                "model": session["model"],
                "git_branch": session["git_branch"],
                "tokens": session["tokens"],
                "cost_usd": session["cost_usd"],
                "session_timestamp": session["timestamp"],
            },
        }
        entries.append(entry)

    save_log(entries)

    # stage the audit log and amend the commit silently
    run(["git", "add", str(AUDIT_LOG)])
    run(["git", "commit", "--amend", "--no-edit", "--no-verify"])


if __name__ == "__main__":
    main()
