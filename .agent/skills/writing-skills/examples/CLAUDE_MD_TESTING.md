# Example: Testing CLAUDE.md

## Scenario
A new developer joins the project and tries to push code that violates the naming convention.

## Expected Behavior
The agent should read `CLAUDE.md`, detect the violation, and block the push.

## Test Result
- **Status**: PASSED
- **Notes**: Correctly identified the `camelCase` vs `snake_case` mismatch in the helper module.
