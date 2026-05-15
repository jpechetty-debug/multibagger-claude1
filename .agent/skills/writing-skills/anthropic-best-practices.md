> Learn how to write effective Skills that Claude can discover and use successfully.

Good Skills are concise, well-structured, and tested with real usage. This guide provides practical authoring decisions to help you write Skills that Claude can discover and use effectively.

### Concise is key
The context window is a public good. Your Skill shares the context window with everything else Claude needs to know.

**Default assumption**: Claude is already very smart. Only add context Claude doesn't already have.

### Set appropriate degrees of freedom
Match the level of specificity to the task's fragility and variability.

**High freedom**: Use when multiple approaches are valid.
**Medium freedom**: Use when a preferred pattern exists.
**Low freedom**: Use when operations are fragile and consistency is critical.

### Naming conventions
Use consistent naming patterns. We recommend using **gerund form** (verb + -ing) for Skill names.

### Writing effective descriptions
The `description` field enables Skill discovery and should include both what the Skill does and when to use it. **Always write in third person**.

### Progressive disclosure patterns
Organize content hierarchically to avoid loading irrelevant context. Use a flat namespace for files within a skill and link directly from `SKILL.md`.

### Use workflows for complex tasks
Break complex operations into clear, sequential steps. Use checklists that Claude can copy and track progress.

### Implement feedback loops
Common pattern: Run validator → fix errors → repeat.

### Template usage
Provide templates for output format. Match the level of strictness to your needs.

### Example-driven development
Create evaluations BEFORE writing extensive documentation. Work with one instance of Claude to create a skill for others.
