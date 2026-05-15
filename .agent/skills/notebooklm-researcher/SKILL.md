---
name: notebooklm-researcher
description: Deep documentation research and synthesis using NotebookLM.
skills: [brainstorming, documentation-templates]
---

# NotebookLM Researcher

Use this skill to analyze high-density documentation and synthesize it into Knowledge Fragments for the agent.

## Protocol

1. **Source Collection**: Identify PDFs, URLs, or text files for research.
2. **Bridge Sync**: Use `mcp_notebooklm_source_add` to upload sources to the bridge.
3. **Deep Query**: Use `mcp_notebooklm_notebook_query` to perform cross-document analysis.
4. **Knowledge Fragment**: Export findings to `openspec/specs/research-{topic}.md`.

## MCP Tools

- `mcp_notebooklm_research_start(topic: string)`
- `mcp_notebooklm_source_add(source_url: string)`
- `mcp_notebooklm_notebook_query(query: string)`

## Goal
Transform "Dark Knowledge" in documentation into actionable specifications.
