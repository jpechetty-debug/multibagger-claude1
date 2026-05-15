# Workflow: OpenSpec Explore (/opsx:explore)

Standard track for discovering and indexing codebase capabilities.

## Trigger
Use when: `exploration`, `index`, `find symbol`, `understand module`.

## Steps

1. **Activation**:
   - Inform: "🤖 Applying knowledge of `@[explorer-agent]`..."
   - Load: `openspec-explore` skill.

2. **Index Check**:
   - Check if index exists. If not, run `mcp_jcodemunch_index_folder "."`.

3. **Symbol Search**:
   - Run `search_symbols` for the user's query.
   - List matching symbols and their locations.

4. **Deep Dive**:
   - For key symbols, run `get_symbol` to understand implementation.
   - Cross-reference with `NotebookLM` if documentation is available.

5. **Documentation**:
   - Create `openspec/specs/exploration-{query-slug}.md`.
   - List: Entry points, key dependencies, and potential change areas.

## Completion
- Present summary of findings.
- Suggest next step: `/opsx:propose`.
