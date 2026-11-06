"""Claude Code hook (Stop / SessionEnd): copy the session transcript into ai-log/transcripts/.

Runs after every Claude reply, so the copy is never more than one turn behind even if the
terminal is closed abruptly. Fail-safe: always exits 0, prints nothing. Standard library only.
"""
import json
import os
import shutil
import sys


def main():
    try:
        raw = sys.stdin.read()
        ev = json.loads(raw) if raw.strip() else {}
        src = ev.get("transcript_path")
        root = os.environ.get("CLAUDE_PROJECT_DIR") or ev.get("cwd") or os.getcwd()
        if src:
            src = os.path.expanduser(src)
        if src and os.path.isfile(src):
            dst_dir = os.path.join(root, "ai-log", "transcripts")
            os.makedirs(dst_dir, exist_ok=True)
            name = (ev.get("session_id") or os.path.splitext(os.path.basename(src))[0]) + ".jsonl"
            shutil.copyfile(src, os.path.join(dst_dir, name))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
