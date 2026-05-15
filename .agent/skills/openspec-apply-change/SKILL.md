---
name: openspec-apply-change
description: Atomic, spec-driven code modifications using OpenSpec delta packets.
skills: [clean-code, tdd-workflow]
---

# OpenSpec Apply Change (opsx-apply)

Use this skill to apply changes derived from a proposal. It ensures that changes are atomic, verified, and documented.

## Protocol

1. **Read Proposal**: Ensure a `proposal.md` exists in `openspec/changes/{task-slug}/`.
2. **Draft Delta**: Create a delta specification in `openspec/changes/{task-slug}/delta.md`.
3. **Execute**: Apply changes using standard file tools.
4. **Verify**: Run `checklist.py` and specific tests.
5. **Archive**: Move the change packet to `openspec/archive/` once verified.

## Safety Gates
- Never apply code without a proposal.
- Every change must have a corresponding test.
- Total changes must be under 300 lines per packet.
