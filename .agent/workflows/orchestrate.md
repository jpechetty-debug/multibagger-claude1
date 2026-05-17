---
description: Coordinate multiple agents for complex tasks that need distinct domain expertise.
---

# /orchestrate - Multi-Agent Orchestration

Use this workflow for complex, cross-domain work. Do not use it for simple one-file edits.

## Complexity Gate

| Task Score | Path |
| ---------- | ---- |
| **SIMPLE CODE**: one file, clear scope | Skip orchestration and invoke the relevant specialist directly |
| **COMPLEX CODE**: multi-file feature/refactor | Create or update a plan first |
| **ORCHESTRATION**: multiple domains or parallel work | Require plan + Socratic Gate |

If the user says "proceed" or provides a complete spec, validate completeness once, record assumptions, and continue.

---

## Agent Selection Matrix

| Task Type | Recommended Agents |
| --------- | ------------------ |
| Web app | `frontend-specialist`, `backend-specialist`, `test-engineer` |
| API | `backend-specialist`, `security-auditor`, `test-engineer` |
| Financial data | `financial-data-engineer`, `database-architect`, `test-engineer` |
| Screener/query work | `financial-data-engineer`, `database-architect`, `performance-optimizer` |
| UI/design | `frontend-specialist`, `performance-optimizer`, `test-engineer` |
| Database | `database-architect`, `backend-specialist`, `security-auditor` |
| Full stack | `project-planner`, `frontend-specialist`, `backend-specialist`, `devops-engineer` |
| Debug | `debugger`, `explorer-agent`, `test-engineer` |
| Security | `security-auditor`, `penetration-tester`, `devops-engineer` |
| Product definition | `product-strategist`, `project-planner`, relevant domain agent |

---

## Available Agents (20 total)

| Agent | Domain | Use When |
| ----- | ------ | -------- |
| `backend-specialist` | Server | API, Node.js, Python, FastAPI |
| `code-archaeologist` | Legacy/code analysis | Risky refactors, old code paths |
| `database-architect` | Data | SQL, PostgreSQL, schema, indexes |
| `debugger` | Debug | Error analysis, broken behavior |
| `devops-engineer` | Ops | CI/CD, Railway, Vercel, deployment |
| `documentation-writer` | Docs | README, manuals, API docs |
| `explorer-agent` | Discovery | Codebase mapping |
| `financial-data-engineer` | Indian market data | Shoonya, NSE/BSE, screener, OHLCV, fundamentals |
| `frontend-specialist` | UI/UX | React, Vite, Next.js, CSS |
| `game-developer` | Games | Unity, Godot, Phaser |
| `mobile-developer` | Mobile | React Native, Flutter |
| `orchestrator` | Meta | Coordination |
| `penetration-tester` | Security testing | Active vulnerability testing |
| `performance-optimizer` | Speed | Profiling, caching, Web Vitals |
| `product-strategist` | Product | PRD, backlog, MVP, acceptance criteria |
| `project-planner` | Planning | Task breakdown, plan files |
| `qa-automation-engineer` | QA automation | Browser automation, CI tests |
| `security-auditor` | Security | Vulnerabilities, auth review |
| `seo-specialist` | SEO | Meta tags, search visibility |
| `test-engineer` | Testing | Unit, integration, E2E |

---

## Execution Protocol

### Phase 1: Planning

1. Read existing plan files if present.
2. If no plan exists for complex work, use `project-planner` to create one.
3. Stop for user approval only when the plan makes scope, schedule, or architecture commitments the user has not already approved.

### Phase 2: Implementation Or Review

After plan and routing are clear:

1. Invoke independent agents in parallel where possible.
2. Give each agent file/module ownership.
3. Tell worker agents they are not alone in the codebase and must not revert edits made by others.
4. Keep test and security verification near the end.

### Context Passing

Every subagent prompt must include:

- Original user request.
- Decisions and assumptions.
- Relevant plan path or summary.
- Prior agent findings.
- Exact responsibility and write scope.

---

## Verification

Run relevant checks before completion:

```bash
python .agent/scripts/checklist.py .
```

For data-layer changes, also run or document the `/data-integrity` workflow.

---

## Output Format

```markdown
## Orchestration Report

### Task
[Original task summary]

### Agents Invoked
| Agent | Focus | Status |
| ----- | ----- | ------ |

### Key Findings
- [Finding]

### Deliverables
- [Artifact]

### Verification
- [Command] -> [Result]
```
