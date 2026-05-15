# Workflow: OpenSpec Archive (/opsx:archive)

Standard track for finalizing and archiving task artifacts.

## Trigger
Use when: `finish`, `done`, `cleanup`, `archive`.

## Steps

1. **Verification**:
   - Confirm all tests pass.
   - Confirm `checklist.py` returns success.

2. **Movement**:
   - Move `openspec/changes/{task-slug}/` to `openspec/archive/{task-slug}/`.
   - Update `ARCHITECTURE.md` if significant structural changes occurred.

3. **Memory Update**:
   - Summarize the change in `claude-mem` or `CHANGELOG.md`.

## Completion
- "Task {task-slug} archived successfully."
