---
name: issue-router
description: Automated issue analysis and resolution. Triggers on commands like "分析 issue", "修 issue", "fix ready", "confirm issue".
license: MIT
metadata:
  author: bk-lite
  version: "2.0"
---

# Issue Router Skill

Recognize and execute issue-router commands from natural language.

---

**Trigger phrases** (match any):
- 分析 issue / analyze issues / 扫描 issue
- 看结果 / show summary / 查看分析结果
- 确认 #N / confirm N / confirm all / 全部确认
- 修 ready 的 / fix ready / 修 direct_fix
- 修 #N / fix issue N / fix N
- 修已确认的 / fix confirmed

---

**Steps**

1. Parse the user's message to determine the command and arguments.

2. Map to the corresponding CLI command:

| Intent | Command |
|--------|---------|
| Analyze/scan issues | `python3 automation/issue-router/issue_bot.py analyze --repo TencentBlueKing/bk-lite` |
| Show summary | `python3 automation/issue-router/issue_bot.py summary` |
| Confirm single issue | `python3 automation/issue-router/issue_bot.py confirm --issue <N>` |
| Confirm all | `python3 automation/issue-router/issue_bot.py confirm --all` |
| Fix ready issues | `python3 automation/issue-router/issue_bot.py fix --ready` |
| Fix single issue | `python3 automation/issue-router/issue_bot.py fix --issue <N>` |
| Fix confirmed | `python3 automation/issue-router/issue_bot.py fix --confirmed` |

3. Execute the command using the Bash tool.

4. Present the output to the user.

---

**Guardrails**
- Always run from the repository root directory
- For `fix` commands, warn the user that code will be modified and committed locally
- Never push to remote
- If the user says a number after "修" or "fix" or "confirm", extract it as the issue number
