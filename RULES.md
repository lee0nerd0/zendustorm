# Rules

## AI
- **Allowed and expected during the build (1:05 to 3:15).** Any tool, any model.
- **Not allowed** during the opening form, the red-pen round, and the final form. Laptops closed or forms only.
- **Log it.** If you use Claude Code, the hooks in `starter/.claude/settings.json` log every prompt and transcript into
  `ai-log/`. Check that `ai-log/prompts.jsonl` appears after your first prompt; if not, tell an invigilator. Don't
  disable them (no `.claude/settings.local.json`, no `disableAllHooks`). With any other tool, export your
  conversations into `ai-log/` before each snapshot and at the freeze.
- Writing your own `CLAUDE.md` (or similar) is fine. Commit it.
- Calling an LLM from inside your system at run time is allowed **only if the replay is reproducible**: same input,
  same output, offline. If in doubt, don't.

## Code
- Start from `starter/`. Make a **private GitHub repo** and invite **`adityasharmazenduit`** as a collaborator.
- **Commit and push about every 20 minutes.** We read the history.
- Any free library, language or framework. List dependencies (`requirements.txt`, `package.json`, …).
- Settings (API URL, file paths, thresholds you choose) go in a config file, not hard-coded. Your API key goes in the
  `FLEET_API_KEY` environment variable, never in git.
- The replay must run **offline** from data you committed in `data/`. `REPLAY_COMMAND` holds the one command we run.

## Timeline (today)
| Time | What |
|---|---|
| 12:30 | Briefing |
| 12:40 to 12:55 | Opening form (no AI) |
| 12:55 to 1:05 | Red-pen round on paper (no AI) |
| 1:05 | Pack password announced. Build starts |
| 1:45 | Snapshot 1 (form). Persona locks |
| 2:15 | Forecast update (second password) |
| 2:45 | Snapshot 2 (form) |
| 3:15 | **Freeze.** Push, submit your freeze commit ID. Then your replay password |
| 3:15 to 3:30 | Run the replay on your frozen code, commit the output, final form (no AI) |
| 3:45 | Presentations, 8 minutes each: demo 3, live what-if card 3, questions 2 |

## Fair play
- Work alone. No talking to other candidates about the task.
- Internet is fine. Google Translate is fine.
- After the freeze, the only commit allowed is `replay/input.json` + `replay/output.json`.
- We re-run your frozen code on the replay input, offline, in a clean container. If it doesn't reproduce your
  output, the replay scores 0.

Questions during the build: raise your hand. Contact: adityasharma@zenduit.com
