# Workflow: OpenSpec Propose (/opsx:propose)

Standard track for drafting atomic change proposals.

## Trigger
Use when: `build`, `implement`, `fix`, `refactor`.

## Steps

1. **Activation**:
   - Inform: "🤖 Applying knowledge of `@[project-planner]`..."
   - Load: `plan-writing`, `brainstorming`.

2. **Research Synthesis**:
   - Read relevant `exploration-*.md` or `research-*.md` from `openspec/specs/`.

3. **Proposal Drafting**:
   - Create `openspec/changes/{task-slug}/proposal.md`.
   - Sections: Goal, Strategy, Files Affected, Verification Plan, Trade-offs.

4. **Socratic Gate**:
   - Ask 3 strategic questions about the proposal.
   - Wait for user feedback.

## Completion
- Provide link to `proposal.md`.
- Suggest next step: `/opsx:apply` once approved.
