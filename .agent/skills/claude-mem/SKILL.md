---
name: claude-mem
description: Memory Layer for persistent context across sessions. Used to provide continuity and remember past architectural decisions, user preferences, and project evolution.
---

# Claude Mem - Memory Layer

> "Continuity is the foundation of intelligence."

## 📋 Overview

Claude Mem is a conceptual skill that ensures the AI maintains a persistent understanding of the project's history, architectural evolution, and user-specific protocols.

## 🛠️ Memory Protocol

### 1. Architectural Memory
- **Source**: `ARCHITECTURE.md`, `GEMINI.md`, and previous task plans (`*.md`).
- **Action**: Always read the most recent 3 task plans before starting a new complex feature.
- **Rule**: If a new decision contradicts a past one, flag it for user review.

### 2. Decision Persistence
- **Action**: Log all major architectural decisions in `ARCHITECTURE.md` under a `## 📜 Decision Log` section.
- **Goal**: Prevent "re-inventing the wheel" or repeating past mistakes.

### 3. User Preferences
- **Action**: Maintain awareness of the user's preferred stack, communication style, and design constraints (e.g., Purple Ban).

## 🔄 Continuity Loop

1. **Session Start**: Read `GEMINI.md` and `PROJECT_MANIFESTO.md`.
2. **Task Start**: Check for existing `{task-slug}.md`.
3. **Execution**: Apply learned patterns from previous successful implementations.
4. **Completion**: Update docs with any new structural findings.
