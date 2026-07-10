# 仓库级 projectmem 与 CodeGraph 退役实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 彻底移除 BK-Lite 仓库维护的 projectmem 与 CodeGraph 集成，并阻止其本地状态目录重新进入版本控制。

**Architecture:** 删除项目级状态、MCP 入口与启动脚本，将统一工具引导收缩为 OpenSpec 单一职责，并把 Agent/运维文档改回不依赖 projectmem 或 CodeGraph 的自包含规则。机器全局安装和其他仓库保持不变。

**Tech Stack:** Bash、JSON、TOML、Markdown、Git ignore

## Global Constraints

- 保留 OpenSpec 以及其他无关的 Agent 工作流。
- 不卸载开发者机器上的全局 `pjm`、`projectmem` 或 `codegraph`。
- 不覆盖当前工作区中已经存在的 `.projectmem/` 删除；将其视为本次清理的一部分。
- 不顺带调整业务代码、依赖或无关 Agent 技能。

---

### Task 1: 移除仓库级运行入口与本地状态

**Files:**
- Delete: `.projectmem/**`
- Delete: `.codegraph/.gitignore`
- Delete: `.mcp.json`
- Delete: `.codex/config.toml`
- Delete: `.claude/settings.json`
- Delete: `scripts/projectmem-mcp`
- Delete: `scripts/codegraph-mcp`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 当前 Git 工作区中已经存在的 `.projectmem/` 删除。
- Produces: 不再自动启动或初始化两个工具的仓库，以及忽略 `.projectmem/`、`.codegraph/` 的 Git 规则。

- [ ] **Step 1: 记录清理前的集成入口**

Run: `git ls-files | rg '(^|/)(\.projectmem|\.codegraph)(/|$)|scripts/(projectmem|codegraph)-mcp|^\.mcp\.json$|^\.codex/config\.toml$'`

Expected: 输出上述项目级状态、配置和 wrapper。

- [ ] **Step 2: 删除项目级入口并添加忽略规则**

在根 `.gitignore` 末尾加入：

```gitignore

# Agent 本地状态（不由本仓库维护）
/.projectmem/
/.codegraph/
```

删除清单中的跟踪文件，并删除仓库内残留的两个本地状态目录；不得删除仓库外文件。

- [ ] **Step 3: 验证入口已移除且状态目录会被忽略**

Run: `git check-ignore -v .projectmem/probe .codegraph/probe`

Expected: 两行均命中根 `.gitignore` 新规则。

Run: `test ! -e .mcp.json && test ! -e .codex/config.toml && test ! -e .claude/settings.json && test ! -e scripts/projectmem-mcp && test ! -e scripts/codegraph-mcp`

Expected: 退出码 0。

### Task 2: 收缩 bootstrap 与当前工作规则

**Files:**
- Modify: `scripts/agent-tooling-bootstrap`
- Modify: `CLAUDE.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: `scripts/agent-tooling-bootstrap [--check]`。
- Produces: 只安装、检查和诊断 OpenSpec 的仓库级 bootstrap；Agent 不再被要求调用两个已退役工具。

- [ ] **Step 1: 建立清理前负向检查**

Run: `rg -n 'pjm|projectmem|codegraph|CodeGraph' scripts/agent-tooling-bootstrap CLAUDE.md docs/operations.md`

Expected: FAIL 语义，输出当前所有待清理入口。

- [ ] **Step 2: 精简 bootstrap**

保留参数 `--check`、`install_node_tool openspec @fission-ai/openspec`、`openspec --version` 与 `openspec doctor`；删除 `--no-index`、uv/projectmem 安装、CodeGraph 安装、hooks 和索引逻辑。最终 usage 为：

```text
usage: scripts/agent-tooling-bootstrap [--check]
```

- [ ] **Step 3: 清理 Agent 与运维文档**

将 `CLAUDE.md` 的基础工具规则改为只检查 `openspec`，删除 CodeGraph 和 projectmem 两个整节；将 `docs/operations.md` 的工具章节改为 OpenSpec 单工具说明和两条命令。

- [ ] **Step 4: 验证脚本与负向检查**

Run: `bash -n scripts/agent-tooling-bootstrap`

Expected: 退出码 0。

Run: `scripts/agent-tooling-bootstrap --check`

Expected: 显示 OpenSpec 版本、`openspec doctor` 结果和 `Agent tooling bootstrap complete.`，退出码 0。

Run: `! rg -n 'pjm|projectmem|codegraph|CodeGraph' scripts/agent-tooling-bootstrap CLAUDE.md docs/operations.md`

Expected: 退出码 0。

### Task 3: 清除误导性的当前依据引用

**Files:**
- Modify: `docs/superpowers/specs/2026-07-09-monitor-default-collection-interval-design.md`
- Modify: `openspec/changes/fix-locale-provider-switch-flash/proposal.md`
- Modify: `server/apps/monitor/tests/test_custom_pull_default_interval.py`
- Modify: `server/apps/monitor/tests/test_plugin_ui_default_interval.py`

**Interfaces:**
- Consumes: 现有业务结论与测试行为。
- Produces: 不依赖已删除项目记忆的自包含说明；不改变任何测试逻辑。

- [ ] **Step 1: 改写说明文字**

删除“见 `.projectmem/summary.md`”和“按 pjm 的 issue 评审”等外部依据，将规则本身直接写入注释或文档；不得修改 Python 断言和测试数据。

- [ ] **Step 2: 运行两个受影响测试**

Run: `cd server && uv run pytest apps/monitor/tests/test_custom_pull_default_interval.py apps/monitor/tests/test_plugin_ui_default_interval.py -q`

Expected: 两个测试文件全部通过。

### Task 4: 仓库级最终验证与提交

**Files:**
- Verify: 本计划涉及的全部文件

**Interfaces:**
- Consumes: Tasks 1-3 的清理结果。
- Produces: 可审阅、无残余活动集成的单一提交。

- [ ] **Step 1: 搜索残余活动集成**

Run: `git grep -n -I -E 'projectmem|ProjectMem|codegraph|CodeGraph|(^|[^[:alnum:]_])pjm([^[:alnum:]_]|$)' -- ':!docs/superpowers/specs/2026-07-10-retire-projectmem-codegraph-design.md' ':!docs/superpowers/plans/2026-07-10-retire-projectmem-codegraph.md'`

Expected: 无输出；退役设计和实施计划是唯一允许保留名称的文档。

- [ ] **Step 2: 检查 diff 与格式**

Run: `git diff --check && git status --short`

Expected: `git diff --check` 退出码 0；状态只包含本计划列出的删除和修改。

- [ ] **Step 3: 提交清理**

```bash
git add .gitignore CLAUDE.md docs/operations.md docs/superpowers/specs/2026-07-09-monitor-default-collection-interval-design.md docs/superpowers/specs/2026-07-10-retire-projectmem-codegraph-design.md docs/superpowers/plans/2026-07-10-retire-projectmem-codegraph.md openspec/changes/fix-locale-provider-switch-flash/proposal.md scripts/agent-tooling-bootstrap server/apps/monitor/tests/test_custom_pull_default_interval.py server/apps/monitor/tests/test_plugin_ui_default_interval.py .projectmem .codegraph .mcp.json .codex/config.toml .claude/settings.json scripts/projectmem-mcp scripts/codegraph-mcp
git commit -m "chore: 退役 projectmem 与 CodeGraph 仓库集成"
```

Expected: 提交成功，且不包含无关文件。
