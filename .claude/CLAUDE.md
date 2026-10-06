<!-- Copyright 2026 Anthropic PBC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Long-running conventions for this project

## Always start here
Before doing anything else, read `PROGRESS.md`. It is your handoff note from the previous session. If it doesn't exist yet, create it now with four sections (`## Done`, `## In progress`, `## Next`, `## Notes`) and leave them empty. Then run `git log --oneline -10` to see what was just committed, and run the project's smoke test (or `npm run build` / `npm test`) once so you know you're starting from a working tree, not a broken handoff.

## One feature at a time
Work on exactly one item from `PROGRESS.md` per session. Finish it (tests passing, screenshot verified) before starting another. If the user gives you a new task mid-session, add it to `PROGRESS.md` and finish the current item first.

## Proof before passing
A test is only "passing" after you have:
1. Run it against the live app (Playwright screenshot or equivalent)
2. Opened the resulting screenshot or console log with the Read tool
3. Confirmed it shows what it should

The `verify-gate` hook will deny writes to `test-results.json` until you have opened evidence. Do not try to work around it.

## Keep `PROGRESS.md` current
After each completed item, update `PROGRESS.md`: check off what's done, add what you learned, note what's next. Future sessions read this file cold.

## Commit often
The `Stop` hook commits tracked changes at session end, but also `git add` new files and commit yourself at meaningful checkpoints with descriptive messages.

## If you're told to stop
`OPERATOR STEERING:` messages come from a human via the steer hook. Treat them as higher priority than your current plan.

## Data quality is a hard gate
- Missing data is `None`, never `0`. Do not write `or 0`, `.get(x, 0)` or `fillna(0)` on fundamentals or signals; the scorer already skips `None`, but it rewards a fake 0 (e.g. D/E 0 = debt-free).
- After any change to data fetching, parsing, scoring inputs or the picks table, run `python -m modules.data_layer.dq_audit` (from `Newmultibagger-main/`). It must exit 0. A full scan runs it automatically and exits 1 on failure.
- Never silence a finding by loosening a threshold. A known issue goes in `WAIVERS` in `modules/data_layer/dq_audit.py` with a reason and a short expiry date.
