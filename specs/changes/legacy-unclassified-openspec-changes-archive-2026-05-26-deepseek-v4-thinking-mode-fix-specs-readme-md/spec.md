# Readme

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/archive/2026-05-26-deepseek-v4-thinking-mode-fix/specs/README.md`。完整内容保留如下。

## No Specification Changes

This change is a **bug fix and code refactoring** that does not introduce new capabilities or modify existing specification-level requirements.

### Rationale

- **Bug fixes**: Correcting `show_think` propagation and `tool_choice` compatibility are implementation fixes, not requirement changes
- **Code refactoring**: Moving inline imports to file head is a code quality improvement with no behavioral impact
- **Encoding fix**: The `_safe_log_preview()` helper only affects log output, not system behavior

All existing specifications remain unchanged.
