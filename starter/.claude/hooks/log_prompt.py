"""Claude Code hook (UserPromptSubmit): append every prompt, word for word, to ai-log/prompts.jsonl.

Fail-safe: never blocks Claude Code, never prints anything (stdout here would be fed to Claude),
always exits 0. Standard library only.
"""
import json
import os
import sys
from datetime import datetime, timezone


def main():
    try:
        raw = sys.stdin.read()
        ev = json.loads(raw) if raw.strip() else {}
        root = os.environ.get("CLAUDE_PROJECT_DIR") or ev.get("cwd") or os.getcwd()
        log_dir = os.path.join(root, "ai-log")
        os.makedirs(log_dir, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": ev.get("session_id"),
            "cwd": ev.get("cwd"),
            "prompt": ev.get("prompt"),
        }
        with open(os.path.join(log_dir, "prompts.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
