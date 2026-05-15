---
name: openspec-explore
description: High-density codebase exploration using jCodeMunch AST indexing.
skills: [clean-code, brainstorming]
---

# OpenSpec Explore (opsx-explore)

Use this skill to perform "Industrial Grade" exploration of the codebase. It leverages `jCodeMunch` for O(1) symbol lookup and 99% token efficiency.

## Protocol

1. **Initialize Index**: If not already indexed, run `mcp_jcodemunch_index_folder`.
2. **Search Symbols**: Use `search_symbols` to find relevant entry points.
3. **Deep Dive**: Use `get_symbol` to read specific implementations without loading entire files.
4. **Synthesize**: Document findings in `openspec/specs/exploration-{slug}.md`.

## MCP Tools

- `mcp_jcodemunch_index_folder(path: string)`
- `search_symbols(query: string)`
- `get_symbol(symbol_name: string)`

## When to Use
- Before any complex refactor.
- When exploring a new codebase or module.
- When token overhead is high.
