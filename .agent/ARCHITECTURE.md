# Antigravity Kit Architecture

> Modular AI agent capability toolkit for the MultiBagger workspace.

---

## Overview

Antigravity Kit is a modular system consisting of:

- **20 specialist agents** - role-based AI personas.
- **46 skill directories** - domain-specific knowledge modules.
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

## Skills (46)

Skill loading uses directory names under `.agent/skills/`.

| Skill | Description |
| ----- | ----------- |
| `api-patterns` | REST, GraphQL, tRPC, API auth, rate limiting, response design |
| `app-builder` | Full-stack app scaffolding and project detection |
| `architecture` | System design patterns and trade-off analysis |
| `bash-linux` | Bash and Linux command guidance |
| `behavioral-modes` | Agent personas and operating modes |
| `brainstorming` | Socratic questioning and discovery |
| `claude-mem` | Persistent context and continuity |
| `clean-code` | Global coding standards |
| `code-review-checklist` | Code review criteria |
| `database-design` | Schema design, indexing, migrations, optimization |
| `deployment-procedures` | CI/CD and deployment workflows |
| `documentation-templates` | Documentation formats and templates |
| `everything-claude-code` | Capability discovery hub |
| `frontend-design` | UI/UX systems, color, motion, typography |
| `game-development` | Game design, audio, 2D/3D, PC/mobile/multiplayer |
| `geo-fundamentals` | Generative-engine optimization |
| `i18n-localization` | Internationalization checks |
| `intelligent-routing` | Agent routing and complexity classification |
| `lint-and-validate` | Lint, validation, and type-coverage scripts |
| `mcp-builder` | Model Context Protocol guidance |
| `mobile-design` | Mobile UX, navigation, performance, testing |
| `nextjs-react-expert` | React and Next.js performance guidance |
| `nodejs-best-practices` | Node.js async, module, and production practices |
| `notebooklm-researcher` | Research and synthesis with NotebookLM-style workflows |
| `openspec-apply-change` | OpenSpec change implementation |
| `openspec-explore` | OpenSpec exploration and requirements discovery |
| `parallel-agents` | Multi-agent orchestration patterns |
| `performance-profiling` | Profiling, Lighthouse, Web Vitals |
| `plan-writing` | Structured task planning |
| `powershell-windows` | Windows PowerShell guidance |
| `python-patterns` | Python, FastAPI, async, Celery, packaging |
| `red-team-tactics` | Offensive security techniques |
| `rust-pro` | Rust systems programming guidance |
| `seo-fundamentals` | SEO, E-E-A-T, technical metadata |
| `server-management` | Server operations and infrastructure management |
| `subagent-driven-development` | Autonomous implementation and review prompts |
| `systematic-debugging` | Debugging workflow and root-cause analysis |
| `tailwind-patterns` | Tailwind utility and styling patterns |
| `tdd-workflow` | Test-driven development |
| `testing-patterns` | Unit, integration, and E2E testing |
| `ui-ux-pro-max` | High-fidelity design intelligence |
| `using-git-worktrees` | Isolated workspaces for parallel development |
| `vulnerability-scanner` | Security scanning and OWASP checks |
| `web-design-guidelines` | Web UI audit rules |
| `webapp-testing` | Playwright and browser verification |
| `writing-skills` | Skill creation and evaluation guidance |

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
| Total skill directories | 46 |
| Total workflows | 16 |
| Root scripts | 4 |
| Skill-level Python scripts | 20 |

---

## Quick Reference

| Need | Agent | Skills |
| ---- | ----- | ------ |
| Product requirements | `product-strategist` | plan-writing, brainstorming |
| Indian market data | `financial-data-engineer` | python-patterns, api-patterns, database-design |
| Web app | `frontend-specialist` | nextjs-react-expert, frontend-design |
| API | `backend-specialist` | api-patterns, nodejs-best-practices |
| Mobile | `mobile-developer` | mobile-design |
| Database | `database-architect` | database-design |
| Security | `security-auditor` | vulnerability-scanner |
| Testing | `test-engineer` | testing-patterns, webapp-testing |
| Debugging | `debugger` | systematic-debugging |
| Planning | `project-planner` | brainstorming, plan-writing |
