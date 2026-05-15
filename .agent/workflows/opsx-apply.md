# Workflow: OpenSpec Apply (/opsx:apply)

Standard track for executing verified code changes.

## Trigger
Use when: `approved`, `proceed`, `execute`.

## Steps

1. **Activation**:
   - Inform: "🤖 Applying knowledge of `@[orchestrator]`..."
   - Load: `openspec-apply-change`, `tdd-workflow`.

2. **Preparation**:
   - Create `openspec/changes/{task-slug}/delta.md` to track applied lines.

3. **Execution**:
   - Write tests first (TDD).
   - Apply implementation code in small chunks.
   - Run tests after each chunk.

4. **Audit**:
   - Run `python .agent/scripts/checklist.py .`.
   - Fix any critical blockers.

## Completion
- Summary of changes made.
- Link to `delta.md`.
- Suggest next step: `/opsx:archive`.
