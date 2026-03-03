---
description: Review a Pull Request following BK-Lite PR review guidelines
---

Review a Pull Request following the BK-Lite review standards.

**Input**: Specify a PR number or URL (e.g., `/pr-review 123` or `/pr-review https://github.com/TencentBlueKing/bk-lite/pull/123`). If omitted, infer from conversation context or prompt the user.

**Steps**

1. **Obtain the PR**

   If a number or URL is provided, use it. Otherwise infer from context or ask.

   Run `gh pr view <number> --json title,body,labels,baseRefName,headRefName` to get metadata.

2. **Get the full diff**

   Run `gh pr diff <number>` to obtain the complete diff.
   Identify all changed files and classify the change type.

3. **Understand the change**

   - Read the PR title, description, and linked Issues
   - Classify the change: bugfix / security hardening / performance optimization / refactoring / new feature / parameter validation
   - Understand the intent and expected behavior

4. **Review each changed file**

   For every changed file:
   1. **Read the original code** — understand the logic before the change
   2. **Read the changed code** — understand the logic after the change
   3. **Judge behavioral differences** — does it change input/output contracts?
   4. **Check the call chain** — search all callers to confirm compatibility

5. **Check red lines (any hit → ❌ reject)**

   - Changes existing API input/output contract without versioning
   - Removes or skips existing validation/permission checks
   - Introduces unverified new dependencies
   - Contains hardcoded secrets, credentials, or internal addresses
   - Silently swallows exceptions (empty `except: pass`)

6. **Note concerns (non-blocking but must mention)**

   - Dead code (branches that never execute)
   - Behavioral changes that depend on frontend/caller coordination but are not documented
   - Missing logs or incorrect log levels
   - Naming inconsistencies or deviation from existing patterns
   - Reimplementation of existing utility functions

7. **Output the review conclusion**

   Use this template:

   ```
   ### Review Conclusion: ✅ Recommend Merge / 🟡 Recommend Merge (with suggestions) / ❌ Do Not Merge

   **Change Type**: bugfix / security hardening / performance optimization / refactoring / new feature
   **Value Assessment**: [one sentence explaining why this is valuable or not]
   **Risk Assessment**: [one sentence on impact to existing logic]

   **Per-file Analysis**:
   1. [filename] — [change summary] — [risk assessment]
   2. ...

   **Suggestions/Questions** (if any):
   - ...
   ```

**Review Criteria**

| Change Type | Value Standard | Risk Focus |
|-------------|---------------|------------|
| **Bugfix** | Reproducible real bug, or obviously wrong logic | Is the fix precise? Does it break normal paths? |
| **Security** | Closes a real attack surface (injection, info leak, etc.) | Does it change how normal requests are handled? |
| **Performance** | Quantifiable improvement (N+1, caching, indexing) | Does it change data consistency or query semantics? |
| **Refactoring** | Eliminates duplication, improves maintainability | Is behavior 100% equivalent? Are all callers adapted? |
| **Validation** | Defends against real invalid input scenarios | Does it reject previously valid input? |
| **New Feature** | Meets clear requirement, reasonable design | Does it affect existing API contracts or data structures? |

**Merge Criteria**

A PR should be recommended for merge only when BOTH conditions are met:
1. **Valuable** — necessary optimization, fix, or change
2. **Non-destructive** — does not break existing business logic

**Guardrails**

- ALWAYS read the original code before judging a change — never review from diff alone
- ALWAYS search for callers of changed functions/APIs to assess compatibility
- NEVER approve a PR that hits any red line
- Keep the review factual and evidence-based — cite specific code when raising concerns
- Do not nitpick style issues unless they deviate significantly from existing codebase patterns
