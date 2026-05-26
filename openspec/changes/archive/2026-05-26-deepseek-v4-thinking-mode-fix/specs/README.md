## No Specification Changes

This change is a **bug fix and code refactoring** that does not introduce new capabilities or modify existing specification-level requirements.

### Rationale

- **Bug fixes**: Correcting `show_think` propagation and `tool_choice` compatibility are implementation fixes, not requirement changes
- **Code refactoring**: Moving inline imports to file head is a code quality improvement with no behavioral impact
- **Encoding fix**: The `_safe_log_preview()` helper only affects log output, not system behavior

All existing specifications remain unchanged.
