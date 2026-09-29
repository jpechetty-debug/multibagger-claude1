# Antigravity Kit Architecture

> Modular AI agent capability toolkit for the MultiBagger workspace.

---

## Overview

Antigravity Kit is a modular system consisting of:

- **20 specialist agents** - role-based AI personas.
- **62 skill directories** - domain-specific knowledge modules (including 10 ECC skills).
- **16 workflows** - slash command procedures.
- **4 root scripts** plus **20 skill-level Python scripts**.

Counts are based on the current filesystem. `.agent/skills/doc.md` is a helper document, not a skill directory.

---

## Directory Structure

```plaintext
.agent/
|-- ARCHITECTURE.md          # This file
|-- agents/                  # 20 specialist agents
|-- skills/                  # 46 skill directories
|-- workflows/               # 16 slash command workflows
|-- rules/                   # Global rules and project manifesto
`-- scripts/                 # Root validation and helper scripts
```

---

## Agents (20)

| Agent | Focus | Primary skills |
| ----- | ----- | -------------- |
| `orchestrator` | Multi-agent coordination | clean-code, parallel-agents, plan-writing, architecture |
| `project-planner` | Discovery, plans, milestones | brainstorming, plan-writing, architecture |
| `product-strategist` | PRDs, user stories, backlog priority | plan-writing, brainstorming, clean-code |
| `financial-data-engineer` | Indian market data, Shoonya, NSE/BSE, financial calculations | python-patterns, api-patterns, database-design, tdd-workflow |
| `frontend-specialist` | Web UI/UX and React/Next.js | nextjs-react-expert, frontend-design, tailwind-patterns |
| `backend-specialist` | APIs, server logic, auth, databases | api-patterns, nodejs-best-practices, python-patterns, database-design |
| `database-architect` | Schema, SQL, migrations, indexing | database-design |
| `mobile-developer` | iOS, Android, React Native, Flutter | mobile-design |
| `game-developer` | Game logic, mechanics, assets | game-development |
| `devops-engineer` | Deployment, CI/CD, production ops | deployment-procedures, server-management |
| `security-auditor` | Security review and compliance | vulnerability-scanner, red-team-tactics |
| `penetration-tester` | Offensive security testing | red-team-tactics |
| `test-engineer` | Test strategy, unit/E2E, TDD | testing-patterns, tdd-workflow, webapp-testing |
| `qa-automation-engineer` | E2E automation and CI quality gates | webapp-testing, testing-patterns |
| `debugger` | Root-cause analysis and fixes | systematic-debugging |
| `performance-optimizer` | Profiling and Web Vitals | performance-profiling |
| `seo-specialist` | Search visibility and GEO | seo-fundamentals, geo-fundamentals |
| `documentation-writer` | Manuals, READMEs, API docs | documentation-templates |
| `code-archaeologist` | Legacy analysis and refactoring | clean-code, code-review-checklist |
| `explorer-agent` | Codebase discovery | read-only exploration |

---

## Skills (62)

Skill loading uses directory names under `.agent/skills/`.

| Skill | Description | Sourced From |
| ----- | ----------- | ------------ |
| `api-patterns` | REST, GraphQL, tRPC, API auth, rate limiting, response design | Core |
| `app-builder` | Full-stack app scaffolding and project detection | Core |
| `architecture` | System design patterns and trade-off analysis | Core |
| `bash-linux` | Bash and Linux command guidance | Core |
| `behavioral-modes` | Agent personas and operating modes | Core |
| `brainstorming` | Socratic questioning and discovery | Core |
| `claude-mem` | Persistent context and continuity | Core |
| `clean-code` | Global coding standards | Core |
| `code-review-checklist` | Code review criteria | Core |
| `context-budget` | Audits agent context consumption and token optimization | ECC |
| `database-design` | Schema design, indexing, migrations, optimization | Core |
| `deployment-procedures` | CI/CD and deployment workflows | Core |
| `documentation-templates` | Documentation formats and templates | Core |
| `everything-claude-code` | Capability discovery hub | Core |
| `fastapi-patterns` | Production FastAPI, Pydantic v2, async lifespan, auth, dependency injection | ECC |
| `frontend-design` | UI/UX systems, color, motion, typography | Core |
| `game-development` | Game design, audio, 2D/3D, PC/mobile/multiplayer | Core |
| `geo-fundamentals` | Generative-engine optimization | Core |
| `i18n-localization` | Internationalization checks | Core |
| `intelligent-routing` | Agent routing and complexity classification | Core |
| `lint-and-validate` | Lint, validation, and type-coverage scripts | Core |
| `llm-trading-agent-security` | Spend limits, execution guards, simulation, prompt injection defenses for trading agents | ECC |
| `mcp-builder` | Model Context Protocol guidance | Core |
| `mobile-design` | Mobile UX, navigation, performance, testing | Core |
| `nextjs-react-expert` | React and Next.js performance guidance | Core |
| `nodejs-best-practices` | Node.js async, module, and production practices | Core |
| `notebooklm-researcher` | Research and synthesis with NotebookLM-style workflows | Core |
| `openspec-apply-change` | OpenSpec change implementation | Core |
| `openspec-explore` | OpenSpec exploration and requirements discovery | Core |
| `parallel-agents` | Multi-agent orchestration patterns | Core |
| `performance-profiling` | Profiling, Lighthouse, Web Vitals | Core |
| `plan-writing` | Structured task planning | Core |
| `ponytail` | Ponytail framework workflow | Core |
| `ponytail-audit` | Code audit with Ponytail patterns | Core |
| `ponytail-debt` | Technical debt management | Core |
| `ponytail-gain` | Capability gain tracking | Core |
| `ponytail-help` | Ponytail guidance and diagnostics | Core |
| `ponytail-review` | Structured Ponytail code review | Core |
| `postgres-patterns` | PostgreSQL query optimization, schema design, indexing, RLS, connection pooling | ECC |
| `powershell-windows` | Windows PowerShell guidance | Core |
| `python-patterns` | Python, FastAPI, async, Celery, packaging | Core |
| `react-performance` | React 18/19 re-render optimization, waterfall elimination, bundle size control | ECC |
| `red-team-tactics` | Offensive security techniques | Core |
| `redis-patterns` | Upstash Redis caching, distributed locks, rate limiting, and pub/sub | ECC |
| `rust-pro` | Rust systems programming guidance | Core |
| `search-first` | Research-before-coding discipline and existing tool evaluation | ECC |
| `security-review` | Security checklists, OWASP principles, secrets, auth, input validation | ECC |
| `seo-fundamentals` | SEO, E-E-A-T, technical metadata | Core |
| `server-management` | Server operations and infrastructure management | Core |
| `subagent-driven-development` | Autonomous implementation and review prompts | Core |
| `systematic-debugging` | Debugging workflow and root-cause analysis | Core |
| `tailwind-patterns` | Tailwind utility and styling patterns | Core |
| `tdd-workflow` | Test-driven development | Core |
| `testing-patterns` | Unit, integration, and E2E testing | Core |
| `ui-ux-pro-max` | High-fidelity design intelligence | Core |
| `using-git-worktrees` | Isolated workspaces for parallel development | Core |
| `verification-loop` | Multi-phase verification loop (build, typecheck, lint, test, security, diff) | ECC |
| `vite-patterns` | Vite bundling, build optimization, dev server speed, and config patterns | ECC |
| `vulnerability-scanner` | Security scanning and OWASP checks | Core |
| `web-design-guidelines` | Web UI audit rules | Core |
| `webapp-testing` | Playwright and browser verification | Core |
| `writing-skills` | Skill creation and evaluation guidance | Core |

---

## Workflows (16)

Slash command procedures live in `.agent/workflows/`.

| Command | Description |
| ------- | ----------- |
| `/brainstorm` | Socratic discovery |
| `/create` | Create new features |
| `/data-integrity` | MultiBagger data layer sanity check |
| `/debug` | Debug issues |
| `/deploy` | Deploy application |
| `/enhance` | Improve existing code |
| `/opsx-apply` | Apply OpenSpec changes |
| `/opsx-archive` | Archive OpenSpec changes |
| `/opsx-explore` | Explore OpenSpec requirements |
| `/opsx-propose` | Propose OpenSpec changes |
| `/orchestrate` | Multi-agent coordination |
| `/plan` | Task breakdown |
| `/preview` | Preview changes |
| `/status` | Check project status |
| `/test` | Run tests |
| `/ui-ux-pro-max` | Design with UI/UX Pro Max |

---

## Skill Loading Protocol

```plaintext
User request
  -> match agent and skill descriptions
  -> read the selected agent file
  -> read each selected SKILL.md
  -> read only the referenced sections/scripts needed for the task
```

### Skill Structure

```plaintext
skill-name/
|-- SKILL.md           # Required metadata and instructions
|-- scripts/           # Optional executable helpers
|-- references/        # Optional templates or docs
`-- assets/            # Optional images, logos, examples
```

---

## Scripts

Root scripts:

| Script | Purpose |
| ------ | ------- |
| `auto_preview.py` | Preview automation helper |
| `checklist.py` | Priority-based validation |
| `session_manager.py` | Session helper |
| `verify_all.py` | Comprehensive verification runner |

Skill-level scripts currently exist under:

- `api-patterns`
- `database-design`
- `frontend-design`
- `geo-fundamentals`
- `i18n-localization`
- `lint-and-validate`
- `mobile-design`
- `nextjs-react-expert`
- `performance-profiling`
- `seo-fundamentals`
- `testing-patterns`
- `ui-ux-pro-max`
- `vulnerability-scanner`
- `webapp-testing`

---

## Statistics

| Metric | Value |
| ------ | ----- |
| Total agents | 20 |
| Total skill directories | 62 |
| Total workflows | 16 |
| Root scripts | 4 |
| Skill-level Python scripts | 20 |
| ECC Rule packs | 3 (`common`, `python`, `react`) |

---

## ECC-Sourced Integrations

The following components were integrated from [affaan-m/ECC](https://github.com/affaan-m/ECC) via a non-overlapping cherry-pick strategy:

### Rule Packs (`.agent/rules/ecc/`)
- `common/`: Coding standards, code review, git workflow, performance, testing conventions
- `python/`: Python standards, FastAPI patterns, security, testing rules
- `react/`: React component architecture, hooks, performance, testing rules

### Curated Skills (10)
- `search-first`: Research-before-coding discipline and existing tool evaluation
- `security-review`: Security checklists, OWASP principles, secrets, auth, input validation
- `fastapi-patterns`: Production FastAPI, Pydantic v2 schemas, async lifespan, auth, dependency injection
- `postgres-patterns`: PostgreSQL query optimization, schema design, indexing, RLS, connection pooling
- `redis-patterns`: Upstash Redis caching, distributed locks, rate limiting, and pub/sub
- `vite-patterns`: Vite bundling, build optimization, dev server speed, and config patterns
- `react-performance`: React 18/19 re-render optimization, waterfall elimination, bundle size control
- `verification-loop`: Multi-phase verification loop (build, typecheck, lint, test, security, diff)
- `llm-trading-agent-security`: Spend limits, execution guards, simulation, prompt injection defenses for trading agents
- `context-budget`: Audits agent context consumption and token optimization

---

## Quick Reference

| Need | Agent | Skills |
| ---- | ----- | ------ |
| Product requirements | `product-strategist` | plan-writing, brainstorming |
| Indian market data | `financial-data-engineer` | python-patterns, api-patterns, database-design, llm-trading-agent-security |
| Web app | `frontend-specialist` | nextjs-react-expert, frontend-design, vite-patterns, react-performance |
| API / Backend | `backend-specialist` | api-patterns, fastapi-patterns, redis-patterns, postgres-patterns |
| Mobile | `mobile-developer` | mobile-design |
| Database | `database-architect` | database-design, postgres-patterns |
| Security | `security-auditor` | vulnerability-scanner, security-review, llm-trading-agent-security |
| Testing | `test-engineer` | testing-patterns, webapp-testing, verification-loop |
| Debugging | `debugger` | systematic-debugging |
| Planning | `project-planner` | brainstorming, plan-writing, search-first |
