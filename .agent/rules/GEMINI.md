---
trigger: always_on
---

# GEMINI.md - Antigravity Kit

> This file defines how AI agents behave in this workspace.

---

## Critical Agent And Skill Protocol

Before implementation, read the relevant agent file, its selected skills, and `.agent/rules/PROJECT_MANIFESTO.md`.

### Project Context Protocol

- Always read `.agent/rules/PROJECT_MANIFESTO.md` at session start.
- Follow the project superpowers: TDD, plan-writing for complex work, and git worktrees when parallel isolation is needed.

### Modular Skill Loading

Agent activated -> check frontmatter `skills:` -> read each selected `SKILL.md` -> read only the referenced sections needed for the task.

- Do not bulk-read every file in a skill folder.
- Rule priority: `GEMINI.md` > agent file > `SKILL.md`.

---

## Request Classifier

Classify the request before choosing agents or plan requirements.

| Request Type | Trigger Keywords | Active Tiers | Result |
| ------------ | ---------------- | ------------ | ------ |
| **QUESTION** | "what is", "how does", "explain" | Tier 0 only | Text response |
| **SURVEY/INTEL** | "analyze", "list files", "overview" | Tier 0 + explorer | Session intel, usually no file edits |
| **SIMPLE CODE** | "fix", "add", "change" with one file and clear scope | Tier 0 + Tier 1 lite | Direct edit, no PLAN.md gate |
| **COMPLEX CODE** | "build", "create", "implement", "refactor" | Tier 0 + Tier 1 full + specialist | Task plan required |
| **DESIGN/UI** | "design", "UI", "page", "dashboard" | Tier 0 + Tier 1 + design agent | Task plan required unless trivially scoped |
| **SLASH CMD** | `/create`, `/orchestrate`, `/debug`, etc. | Command-specific | Follow workflow |

---

## Intelligent Agent Routing

Before responding, select the best agent(s) for the request.

1. Detect domains: frontend, backend, database, security, data, product, testing, DevOps, documentation.
2. Select the smallest effective agent set.
3. Inform the user which expertise is being applied when the prompt system requires visible routing.
4. Apply the selected agent's principles and loaded skills.

### Routing Hints

| Need | Preferred agent |
| ---- | --------------- |
| Product requirements, PRD, user stories | `product-strategist` |
| Shoonya, NSE/BSE, screener, market data | `financial-data-engineer` |
| API, auth, server logic | `backend-specialist` |
| React, Vite, UI, hooks | `frontend-specialist` |
| Schema, SQL, indexing | `database-architect` |
| Tests and coverage | `test-engineer` |
| Security review | `security-auditor` |
| Production deployment | `devops-engineer` |

---

## Tier 0: Universal Rules

### Domain Context (MultiBagger Project)

- All market timestamps use IST (UTC+5:30). In Python, prefer `datetime.now(ZoneInfo("Asia/Kolkata"))`.
- Market hours are 09:15-15:30 IST, Monday-Friday, subject to the NSE trading calendar.
- Shoonya is the data source authority. Do not add yfinance or scraping.
- Do not hardcode NSE instrument tokens. Read token mappings from the database and refresh them through the approved Shoonya flow.
- Financial calculations must handle `None`, missing values, and zero denominators gracefully.
- Upstash Redis REST credentials are not interchangeable with native Redis TCP URLs. Celery requires a `rediss://` URL.

### Complexity Gate

Use this before requiring a plan file or specialist orchestration.

| Task Score | Path |
| ---------- | ---- |
| **SIMPLE CODE**: one file, clear scope, low blast radius | Skip PLAN.md check and invoke the relevant specialist directly |
| **COMPLEX CODE**: multi-file change, new feature, shared behavior | Require a task plan before implementation |
| **ORCHESTRATION**: multi-agent or cross-domain work | Require a task plan and Socratic Gate |

### Language Handling

When the user's prompt is not in English:

1. Internally translate for comprehension.
2. Respond in the user's language.
3. Keep code comments and identifiers in English unless the codebase uses another convention.

### Clean Code

All code must follow `clean-code` principles:

- Concise, direct, self-documenting implementation.
- Tests sized to risk and blast radius.
- Performance measured before optimization.
- Secrets and production safety verified.

### File Dependency Awareness

Before modifying a file:

1. Check any available system map or architecture note.
2. Identify dependent files.
3. Update affected files together when the contract changes.

### System Map Read

Read `.agent/ARCHITECTURE.md` at session start to understand current agents, skills, workflows, and scripts.

---

## Tier 1: Code Rules

### Project Type Routing

| Project Type | Primary Agent | Skills |
| ------------ | ------------- | ------ |
| **MOBILE**: iOS, Android, React Native, Flutter | `mobile-developer` | mobile-design |
| **WEB**: React, Vite, Next.js | `frontend-specialist` | frontend-design, nextjs-react-expert |
| **BACKEND**: API, server, DB | `backend-specialist` | api-patterns, database-design |
| **FINANCIAL DATA**: Shoonya, NSE/BSE, fundamentals | `financial-data-engineer` | python-patterns, api-patterns, database-design |

Mobile tasks must route to `mobile-developer`, not `frontend-specialist`.

### Socratic Gate

Ask questions only when they materially reduce risk or ambiguity.

| Request Type | Strategy | Required Action |
| ------------ | -------- | --------------- |
| **New Feature / Build** | Discovery | Ask up to 3 strategic questions if requirements are incomplete |
| **Code Edit / Bug Fix** | Context check | Confirm assumptions when impact is unclear |
| **Vague / Simple** | Clarification | Ask the smallest useful scope question |
| **Full Orchestration** | Gatekeeper | Pause specialist subagents until plan and routing are clear |
| **Direct "proceed" / "just do it" with full spec** | Validation | Validate completeness once, document assumptions, proceed |

Protocol:

1. If material requirements are unclear, ask.
2. If the user provides a complete spec, proceed after recording assumptions.
3. If the user says "proceed", "just do it", or equivalent, do not force extra edge-case questions before execution.
4. Capture unresolved edge cases in plan, review notes, or final report.
5. Do not invoke multi-agent orchestration until the plan and routing are clear.

### Final Checklist Protocol

When the user asks for final checks, run validation in priority order:

1. Security.
2. Lint and type checks.
3. Schema validation.
4. Tests.
5. UX/SEO/performance checks where relevant.

Common commands:

```bash
python .agent/scripts/checklist.py .
python .agent/scripts/verify_all.py .
```

### Mode Mapping

| Mode | Agent | Behavior |
| ---- | ----- | -------- |
| **plan** | `project-planner` | Research and plan before code |
| **ask** | none | Answer and clarify |
| **edit** | relevant specialist or `orchestrator` | Execute with the complexity gate |

---

## Tier 2: Design Rules

Design rules live in specialist agents:

| Task | Read |
| ---- | ---- |
| Web UI/UX | `.agent/agents/frontend-specialist.md` |
| Mobile UI/UX | `.agent/agents/mobile-developer.md` |

---

## Quick Reference

- Master coordination: `orchestrator`
- Planning: `project-planner`
- Product: `product-strategist`
- Financial data: `financial-data-engineer`
- Backend/API: `backend-specialist`
- Frontend/UI: `frontend-specialist`
- Database: `database-architect`
- Testing: `test-engineer`
- Security: `security-auditor`
- Debugging: `debugger`

Key skills: `clean-code`, `brainstorming`, `plan-writing`, `intelligent-routing`, `api-patterns`, `database-design`, `python-patterns`, `nextjs-react-expert`, `frontend-design`.
