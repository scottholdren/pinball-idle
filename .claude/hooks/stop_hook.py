#!/usr/bin/env python3
"""
Claude Code Stop hook.
Reads session data from stdin, parses the transcript JSONL,
sums token usage, and writes to a temp file for the post-commit hook.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone


def sum_tokens(transcript_path: str) -> dict:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    model = None
    git_branch = None

    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # grab model and branch from any assistant message
                if obj.get("type") == "assistant":
                    msg = obj.get("message", {})
                    if model is None and msg.get("model"):
                        model = msg["model"]
                    if git_branch is None and obj.get("gitBranch"):
                        git_branch = obj["gitBranch"]

                    usage = msg.get("usage", {})
                    for field in totals:
                        totals[field] += usage.get(field) or 0

    except FileNotFoundError:
        pass

    return {**totals, "model": model, "git_branch": git_branch}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit(0)

    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = hook_input.get("session_id", "unknown")
    transcript_path = hook_input.get("transcript_path", "")

    if not transcript_path or not Path(transcript_path).exists():
        sys.exit(0)

    token_data = sum_tokens(transcript_path)

    # estimate cost using claude sonnet 4.6 pricing as default
    # input: $3/MTok, output: $15/MTok, cache_read: $0.30/MTok, cache_write: $3.75/MTok
    input_cost    = (token_data["input_tokens"] / 1_000_000) * 3.00
    output_cost   = (token_data["output_tokens"] / 1_000_000) * 15.00
    cache_read    = (token_data["cache_read_input_tokens"] / 1_000_000) * 0.30
    cache_write   = (token_data["cache_creation_input_tokens"] / 1_000_000) * 3.75
    cost_usd      = round(input_cost + output_cost + cache_read + cache_write, 6)

    payload = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transcript_path": transcript_path,
        "model": token_data["model"],
        "git_branch": token_data["git_branch"],
        "tokens": {
            "input": token_data["input_tokens"],
            "output": token_data["output_tokens"],
            "cache_creation": token_data["cache_creation_input_tokens"],
            "cache_read": token_data["cache_read_input_tokens"],
        },
        "cost_usd": cost_usd,
    }

    tmp_path = Path(f"/tmp/claude-audit-{session_id}.json")
    tmp_path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
