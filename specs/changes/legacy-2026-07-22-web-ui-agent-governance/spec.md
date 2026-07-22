# Historical Superpowers change: 2026-07-22-web-ui-agent-governance

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-22-web-ui-agent-governance.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有读取仓库 Agent 入口的 Code Agent 在修改 Web 页面、组件或样式前，先检索并复用统一组件，确实不适用时才创建 app-local 组件。

**Architecture:** 在仓库单一 Agent 真相源 `CLAUDE.md` 增加 Web UI 任务触发规则；`AGENTS.md` 通过现有软链接自动获得同一规则，不维护第二份副本。规则只约束 Agent 工作流，不增加阻断式 CI。

**Tech Stack:** Markdown、Git symlink、现有 `web/DESIGN.md`、`web/COMPONENT_GOVERNANCE.md`、Storybook、组件所有权审计。

## Global Constraints

- 不新增阻断式 CI 或 lint 规则。
- 已有统一组件可承载时优先复用，允许通过稳定 variant 扩展。
- 确实不适用且只有一个 app 消费时，组件放入 `web/src/app/<app>/components`。
- 未出现两个以上真实 app 消费前，不得把业务组件放入 `web/src/components`。
- `CLAUDE.md` 是 Agent 规则唯一编辑点；不得直接改 `AGENTS.md` 软链接副本。
- 保留当前工作树中的 Monitor 未提交改动，不纳入本任务提交。

---

### Task 1: 接入 Web UI Agent 前置流程

**Files:**
- Modify: `CLAUDE.md`
- Reference: `web/DESIGN.md`
- Reference: `web/COMPONENT_GOVERNANCE.md`

**Interfaces:**
- Consumes: 根目录 Agent 启动时自动加载的 `CLAUDE.md` / `AGENTS.md` 规则。
- Produces: “Web UI / 组件任务”触发块，供不同 Code Agent 在写代码前执行相同检索与放置流程。

- [ ] **Step 1: 验证规则尚未接入**

Run:

```bash
! rg -n "Web UI / 组件任务（强制前置）" CLAUDE.md
```

Expected: 命令退出 0，证明当前入口不存在该触发块。

- [ ] **Step 2: 在 Agent 执行规则中加入触发块**

在 `CLAUDE.md` 的“项目快捷工作流”之后加入：

```markdown
- **Web UI / 组件任务（强制前置）**：修改 `web/` 下页面、组件、样式或 Storybook 前，必须先阅读 `web/DESIGN.md` 与 `web/COMPONENT_GOVERNANCE.md`，并按以下顺序执行：
  1. 搜索 Ant Design、`web/src/components`、当前 `web/src/app/<app>/components` 和 Storybook，禁止凭记忆新建组件。
  2. 已有组件能承载时必须复用；仅样式差异优先增加稳定 variant，不复制源码或创建平行实现。
  3. 确实不适用且只有一个 app 使用时，在 `web/src/app/<app>/components` 创建 app-local 组件。
  4. 只有两个及以上真实 app 已接入同一抽象后，才可提升到 `web/src/components`；shared 组件变化必须同步 Storybook。
  5. 交付时说明复用了哪个组件；若新建，说明现有组件不适用的理由与组件归属。
```

- [ ] **Step 3: 验证入口、软链接和引用文件**

Run:

```bash
test -L AGENTS.md
test "$(readlink AGENTS.md)" = "CLAUDE.md"
test -f web/DESIGN.md
test -f web/COMPONENT_GOVERNANCE.md
rg -n "Web UI / 组件任务（强制前置）" CLAUDE.md AGENTS.md
git diff --check
```

Expected: 全部命令退出 0，`CLAUDE.md` 与 `AGENTS.md` 命中同一规则且无空白错误。

- [ ] **Step 4: 复核变更范围**

Run:

```bash
git status --short
git diff -- CLAUDE.md
```

Expected: 本任务只新增 `CLAUDE.md` 的 Agent 触发块；既有 Monitor 修改保持未暂存。

- [ ] **Step 5: 提交 Agent 入口规则**

```bash
git add CLAUDE.md
git commit -m "docs(agent): 接入 Web 组件复用前置规则"
```

Expected: 提交仅包含 `CLAUDE.md`。
