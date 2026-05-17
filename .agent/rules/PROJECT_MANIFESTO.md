# Project Manifesto: Sovereign Dashboard & LMS

> This document defines the core mission, values, and workflow for the current project. All agents must adhere to these principles.

---

## 🎯 Core Objective
Build a world-class **Sovereign Trading Dashboard** and **AI-Native LMS** that leverages high-fidelity UI/UX and resilient backend architecture.

## Technical Constraints (All Agents Must Know)

- **Platform**: Indian equity markets (NSE/BSE), not a global platform.
- **Data Source**: Shoonya (Finvasia) API only. Do not add yfinance or scraping.
- **Backend**: FastAPI (Python) on Railway. Use async/await for I/O-bound work.
- **Frontend**: React + Vite on Vercel. Use TanStack Query for server state and Zustand for client state.
- **Database**: Neon PostgreSQL. SQLite is banned for production because write-locking is incompatible with multi-worker deployment.
- **Cache**: Upstash Redis. Use REST credentials for REST clients; Celery and standard Redis clients require the `rediss://` TCP URL.
- **Auth**: Shoonya unattended refresh requires TOTP automation via `pyotp`.
- **Market Hours**: IST (UTC+5:30). Cron schedules must account for Indian market hours and holidays.
- **Cost Ceiling**: Keep recurring infrastructure under Rs. 500/month unless a plan explicitly approves higher spend.

## 🛠️ The "Antigravity" Workflow (Superpowers)

All agents are "trained" to use the following process engine:

1.  **TDD (Test-Driven Development)**: Write tests before implementing logic. No code is complete without passing verification.
2.  **Plan-writing**: Every complex task starts with a `{task-slug}.md` plan in the project root.
3.  **Git Worktrees**: Manage isolated workspaces for parallel feature development.
4.  **UI/UX Pro Max**: Apply "Design Intelligence" to every component. Avoid safe harbors, reject cliches, and ensure 100% uniqueness.

## 🧠 Memory & Continuity (Claude Mem)

- **Persistent Context**: Use `claude-mem` to maintain architectural continuity across sessions.
- **Decision Integrity**: Respect past decisions documented in `ARCHITECTURE.md` and previous plan files.

## 🎨 Design Philosophy (UI/UX Pro Max)

- **Radical Topology**: Reject standard "Hero Splits" and "Bento Grids".
- **Purple Ban**: ❌ No purple/indigo/magenta unless requested.
- **Extremism**: Choose between extreme Sharp (0px) or extreme Rounded (32px) edges.
- **Premium Depth**: Use overlapping elements, grain textures, and staggered animations.

## 📦 Capability Discovery (Everything Claude Code)

- Constantly seek to improve the toolkit by integrating new skills and resources from the `everything-claude-code` directory.

---

## ✅ Success Definition
The project is successful when:
1. All `checklist.py` and `verify_all.py` audits pass with zero critical errors.
2. The UI achieves the "Trinity": Sharp/Net Geometry, Bold Color Palette, and Fluid Animation.
3. The codebase is self-documenting and strictly typed.
