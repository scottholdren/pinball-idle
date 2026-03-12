# claude-audit

Automatically associates Claude Code token usage and cost with git commits.

Every time Claude Code finishes a session, this tool records what it did, what it cost, and links that data to the resulting git commit. Over time the log becomes a record of AI-assisted development activity you can query against the GitHub API to report cost per PR, per branch, or per developer.

---

## How it works

Two hooks work together:

**Claude Code Stop hook** (`stop_hook.py`)

Fires when Claude Code finishes responding. It:
1. Checks for unstaged file changes and auto-commits them with a message listing the changed files
2. Parses the session transcript JSONL to sum token usage across all assistant messages
3. Estimates cost using Anthropic's published pricing for the detected model
4. Writes a temp file to `/tmp/claude-audit-{session_id}.json`

**Git post-commit hook** (`post-commit`)

Fires after every git commit. It:
1. Looks for Claude session temp files in `/tmp` written in the last 30 minutes
2. Reads the current commit hash, message, author, and changed files from git
3. Merges the session data with the commit data
4. Appends the combined entry to `.claude-audit/log.json`
5. Stages the log file and amends the commit to include it
6. Renames consumed temp files to `.done` to prevent double-counting

---

## Data format

Each entry in `.claude-audit/log.json` looks like this:

```json
{
  "commit": "e353fe9f8ab9e662748c0ab975c6e55b3c09ccee",
  "timestamp": "2026-03-12T04:38:09-04:00",
  "message": "Change background color to red",
  "author": "Scott Holdren",
  "files_changed": [
    "src/index.css"
  ],
  "claude": {
    "session_id": "57eae8cc-dc76-445c-8579-7dc68521b6f4",
    "model": "anthropic/claude-4.6-sonnet-20260217",
    "git_branch": "master",
    "tokens": {
      "input": 12,
      "output": 359,
      "cache_creation": 5163,
      "cache_read": 62796
    },
    "cost_usd": 0.043621,
    "session_timestamp": "2026-03-12T08:37:39.485614+00:00"
  }
}
```

Commits with no Claude session have no `claude` key. This is intentional - it distinguishes human-only commits from AI-assisted ones.

---

## Token fields

Claude Code sessions generate four categories of tokens:

| Field | Description | Pricing (Sonnet 4.6) |
|---|---|---|
| `input` | Direct prompt tokens | $3.00 / MTok |
| `output` | Response tokens | $15.00 / MTok |
| `cache_creation` | Tokens written to cache (system prompt, context) | $3.75 / MTok |
| `cache_read` | Tokens read from cache on subsequent messages | $0.30 / MTok |

Cache creation is billed once per session at a slightly higher rate. Cache reads on subsequent messages in the same session are much cheaper. This is why the first session in a project costs more - the system prompt is being cached for the first time.

---

## Transcript format

Claude Code writes session transcripts as JSONL files to:
```
~/.claude/projects/{project-path}/{session-id}.jsonl
```

Each line is a JSON object. The stop hook reads assistant messages and sums the `usage` block on each:

```json
{
  "type": "assistant",
  "sessionId": "57eae8cc-...",
  "message": {
    "model": "anthropic/claude-4.6-sonnet-20260217",
    "usage": {
      "input_tokens": 12,
      "output_tokens": 359,
      "cache_creation_input_tokens": 5163,
      "cache_read_input_tokens": 62796
    }
  }
}
```

---

## Setup

**1. Copy the hooks into your project:**

```bash
mkdir -p .claude/hooks
cp stop_hook.py .claude/hooks/stop_hook.py
chmod +x .claude/hooks/stop_hook.py

cp post_commit.py .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

**2. Initialize the audit log:**

```bash
mkdir -p .claude-audit
echo "[]" > .claude-audit/log.json
git add .claude-audit/log.json
```

**3. Register the stop hook in `.claude/settings.json`:**

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/.claude/hooks/stop_hook.py"
          }
        ]
      }
    ]
  }
}
```

Use an absolute path. Claude Code may not run hooks from the project directory.

**4. Restart Claude Code.**

Hooks are snapshotted at session start. Changes to `settings.json` require a full restart to take effect.

---

## Known limitations

**The post-commit hook lives outside version control.** Git does not track `.git/hooks/`, so every developer who clones the repo must manually copy `post_commit.py` to `.git/hooks/post-commit` and make it executable. A setup script is the recommended way to handle this.

**Pricing is hardcoded for Sonnet 4.6.** If your team uses multiple models the cost estimates will be inaccurate for non-Sonnet sessions. The model name is captured in the log so you can recalculate with correct pricing later.

**Manual commits between Claude sessions may miss data.** If you commit manually before Claude Code finishes its session the temp file won't exist yet and that commit gets no audit entry.

**The 30-minute window.** The post-commit hook only looks back 30 minutes for temp files. Long sessions followed by delayed commits may not associate correctly. Extend `SESSION_MAX_AGE_MINUTES` in `post_commit.py` if needed.

---

## Reporting

The log is designed to be joined with the GitHub API. Given a PR number you can:

1. Fetch all commits in the PR via the GitHub API
2. Look up each commit hash in `log.json`
3. Sum `cost_usd` across matching entries

This gives you total AI cost per PR, which rolls up to cost per feature branch or per developer over any time window.
