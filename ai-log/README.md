# ai-log/ (commit this folder)

**Claude Code users:** do nothing. The hooks in `.claude/settings.json` write
- `prompts.jsonl`: every prompt you type, word for word, with a timestamp
- `transcripts/<session>.jsonl`: the full session, refreshed after every reply

**Check it works:** after your first prompt, `ai-log/prompts.jsonl` should exist. If it doesn't (some Windows
setups), tell an invigilator, keep going, and at each snapshot copy your session files from
`~/.claude/projects/<this-project>/*.jsonl` into `ai-log/transcripts/`.

Do not add `.claude/settings.local.json` and do not set `disableAllHooks`. The freeze check looks for both,
and for gaps in the prompt log while you were committing code.

**Any other AI tool** (Cursor, Copilot Chat, ChatGPT, Gemini, Codex, …): export or copy your
conversation into this folder before each snapshot (1:45, 2:45) and at the freeze (3:15).
A plain `.md` or `.txt` per session is fine. Name it `<tool>-<time>.md`.

Using AI is allowed and expected during the build. Hiding it is not.
