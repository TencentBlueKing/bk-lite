# Historical Superpowers change: 2026-07-16-web-component-governance-master-merge

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-16-web-component-governance-master-merge.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将本地 `master` 的 211 个新增提交合入 `codex/web-component-governance-merged`，保留 Storybook-first 组件治理成果并吸收主线业务修复。

**Architecture:** 先将当前约 60 个修改、14 个删除及约 300 个未跟踪治理入口固化为 checkpoint，再执行真实 merge。冲突按 shared/Storybook、app consumer、删除/迁移三类逐项裁决，禁止全局选择 ours/theirs。

**Tech Stack:** Git、Next.js 16、React 19、TypeScript、pnpm、Storybook

## Global Constraints

- shared component 的边界、公共 API、目录归属和 Storybook 契约以治理分支为骨架。
- app 业务流程、接口字段、权限逻辑和主线 bugfix 以 `master` 为准。
- 已迁移到新 source of truth 的旧实现继续删除；master 新逻辑移植到新契约。
- 不删除既有 stash，不使用 `git reset --hard`、`git checkout --` 或全仓 ours/theirs。
- 只处理 merge 及其直接引发的引用、类型、Storybook 和运行时问题。

---

### Task 1: 建立合并前证据与基线

**Files:**
- Inspect: 全工作区 Git 状态
- Verify: `web/package.json`

**Interfaces:**
- Consumes: 当前治理 WIP、本地 `master=5d572c848`
- Produces: 可比较的 Git 清单和合并前门禁结果

- [ ] **Step 1: 保存 Git 状态与对象引用**

Run:

```bash
git status --porcelain=v2 --branch > /tmp/web-component-governance-premerge-status.txt
git stash list > /tmp/web-component-governance-premerge-stashes.txt
git rev-parse HEAD master > /tmp/web-component-governance-premerge-refs.txt
```

Expected: 三个文件非空，且 `master` 解析为 `5d572c84853d...`。

- [ ] **Step 2: 检查未跟踪文件是否包含不应提交的运行时产物**

Run:

```bash
git status --short | rg '^\?\?' | rg '(\.env$|node_modules|\.next|coverage|dist|storybook-static|\.DS_Store)' || true
```

Expected: 无 secrets、依赖目录或构建产物；如命中则从 checkpoint 排除。

- [ ] **Step 3: 运行合并前 TypeScript 基线**

Run:

```bash
cd web && pnpm type-check
```

Expected: exit 0；若失败，完整保存输出并标记为合并前基线。

- [ ] **Step 4: 运行合并前 ESLint 基线**

Run:

```bash
cd web && pnpm lint
```

Expected: exit 0；若失败，完整保存输出并标记为合并前基线。

### Task 2: 固化治理成果 checkpoint

**Files:**
- Add: 当前治理工作区全部非忽略源码、stories、fixtures 与治理文档
- Exclude: `.env`、`.next`、`node_modules`、构建产物和 secrets

**Interfaces:**
- Consumes: Task 1 的文件清单与基线
- Produces: 可恢复的治理成果 checkpoint commit

- [ ] **Step 1: 暂停前端 dev 进程避免生成文件变化**

Run: 向当前 Next dev session 发送 `Ctrl-C`。

Expected: `3000` 不再监听。

- [ ] **Step 2: 暂存治理成果并审计 staged diff**

Run:

```bash
git add -A
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only | rg '(\.env$|node_modules|\.next|coverage|dist|storybook-static|\.DS_Store)' && exit 1 || true
```

Expected: diff check 通过，staged 集合不含本地配置或生成物。

- [ ] **Step 3: 创建 checkpoint commit**

Run:

```bash
git commit -m "refactor(web): 保存 Storybook-first 组件治理成果"
```

Expected: commit 成功，`git status --short` 为空或只剩明确排除的本地文件。

### Task 3: 合并本地 Master 并分类解决冲突

**Files:**
- Modify: `git diff --name-only --diff-filter=U` 返回的全部冲突文件
- Preserve: shared components、barrels、stories、fixtures、治理文档
- Integrate: master 的 app 业务逻辑、接口字段、权限逻辑与 bugfix

**Interfaces:**
- Consumes: checkpoint commit 与 `master=5d572c84853d...`
- Produces: 无未合并索引项的 merge 工作树

- [ ] **Step 1: 执行真实 merge**

Run:

```bash
git merge --no-ff master
```

Expected: 进入 merge 状态；若有冲突，`git diff --name-only --diff-filter=U` 给出完整清单。

- [ ] **Step 2: 按职责生成冲突清单**

Run:

```bash
git diff --name-only --diff-filter=U | sort
git status --short
```

Expected: 将冲突分为 shared/Storybook、app consumer、删除/迁移、配置/工具链四组。

- [ ] **Step 3: 解决 shared 与 Storybook 冲突**

Run to materialize every conflict stage for side-by-side review:

```bash
rm -rf /tmp/governance-conflicts && mkdir -p /tmp/governance-conflicts
git diff --name-only --diff-filter=U -z | while IFS= read -r -d '' file; do
  key=$(printf '%s' "$file" | shasum | cut -d' ' -f1)
  git show ":2:$file" > "/tmp/governance-conflicts/$key.ours" 2>/dev/null || true
  git show ":3:$file" > "/tmp/governance-conflicts/$key.theirs" 2>/dev/null || true
done
```

Expected: 每个存在对应 stage 的冲突都有 ours/theirs 快照；保留治理契约并合入 master 新行为，任何 props/行为改变同步到 stories/fixtures，然后逐文件 `git add`。

- [ ] **Step 4: 解决 app consumer 冲突**

Run to补充每个冲突的 merge-base 快照，再逐文件保留 master 业务行为与治理后的 shared imports：

```bash
git diff --name-only --diff-filter=U -z | while IFS= read -r -d '' file; do
  key=$(printf '%s' "$file" | shasum | cut -d' ' -f1)
  git show ":1:$file" > "/tmp/governance-conflicts/$key.base" 2>/dev/null || true
done
```

Expected: app 不恢复已治理掉的重复 UI 实现，且 master 新字段、请求和权限逻辑不丢失。

- [ ] **Step 5: 解决删除与迁移冲突**

Run to collect removed and renamed paths, then use the emitted basenames/symbol names for targeted `rg` checks：

```bash
git status --short | rg '^(UD|DU|DD|R.|.R)' | tee /tmp/governance-delete-rename-conflicts.txt
git diff --name-only --diff-filter=U | while IFS= read -r file; do
  basename "$file"
done | sort -u > /tmp/governance-conflict-basenames.txt
```

Expected: 已迁移 source of truth 时继续删除旧入口；master 的真实新增逻辑迁入新入口后再暂存。

- [ ] **Step 6: 检查冲突标记和索引状态**

Run:

```bash
git diff --name-only --diff-filter=U
rg -n '^(<<<<<<<|=======|>>>>>>>)' web docs || true
git diff --cached --check
```

Expected: 无未合并文件、无冲突标记、diff check 通过。

### Task 4: 修复合并引入的静态与 Storybook 回归

**Files:**
- Modify: 仅限 Task 3 merge 直接造成的类型、lint、引用或 Storybook 失败文件
- Test: 相关 stories/fixtures 与 shared component contracts

**Interfaces:**
- Consumes: 无索引冲突的 merge 工作树
- Produces: 静态门禁和 Storybook 可构建结果

- [ ] **Step 1: 运行 TypeScript 门禁**

Run:

```bash
cd web && pnpm type-check
```

Expected: exit 0；失败时逐项判断是否为 merge 新增，仅修直接回归。

- [ ] **Step 2: 运行 ESLint 门禁**

Run:

```bash
cd web && pnpm lint
```

Expected: exit 0；不做全仓格式化。

- [ ] **Step 3: 运行 Storybook build**

Run:

```bash
cd web && pnpm build-storybook
```

Expected: exit 0；所有 shared stories 和 fixtures 可解析。

- [ ] **Step 4: 提交 merge**

Run:

```bash
git add -A
git commit
```

Expected: 创建包含两个 parent 的 merge commit，提交信息使用中文说明冲突裁决原则。

### Task 5: 运行时 Smoke 与最终完整性验证

**Files:**
- Verify: Web 本地运行时，不新增业务文件

**Interfaces:**
- Consumes: 完成的 merge commit
- Produces: 可交付的 Git、静态、Storybook 与页面验证证据

- [ ] **Step 1: 启动 Web 并确认端口**

Run:

```bash
cd web
PATH=/Users/qiu/.nvm/versions/node/v20.18.3/bin:$PATH pnpm dev
```

Expected: Next dev ready，监听 `0.0.0.0:3000`。

- [ ] **Step 2: 验证代表性路由与代理接口**

Run:

```bash
/usr/bin/curl --noproxy '*' -f http://127.0.0.1:3000/api/proxy/core/api/get_bk_settings -o /tmp/bk-settings.json
```

Expected: HTTP 200；浏览器验证登录、ops-console、cmdb、monitor、opspilot、job、alarm 代表入口。

- [ ] **Step 3: 验证 Git 完整性**

Run:

```bash
git status --short
git show --no-patch --format='%H%n%P%n%s' HEAD
git merge-base --is-ancestor master HEAD
```

Expected: 工作区无意外源码改动；HEAD 有两个 parent；master 是 HEAD ancestor。

- [ ] **Step 4: 汇总候选、跨应用差异、迁移与 Storybook 决策**

Expected: 最终报告按用户要求列出冲突涉及的组件候选、跨应用差异、shared 决策、迁移路径与 stories 更新，并明确任何残余风险。

## specs: 2026-07-16-web-component-governance-master-merge-design.md

## 背景

`codex/web-component-governance-merged` 是 Storybook-first 的前端组件治理分支。当前工作区承载大量尚未提交的 shared component、Storybook stories/fixtures、应用迁移与重复实现清理；本地 `master` 已更新到 `5d572c848`，治理分支相对其落后 211 个提交。

本次工作的目标不是用一侧代码整体覆盖另一侧，而是在吸收 master 最新业务修复的同时，保住治理分支已经形成的组件契约、复用边界与 Storybook 事实源。

## 合并策略

采用“治理成果 checkpoint + 常规 merge + 语义化解冲突”策略：

1. 对当前治理工作区做完整状态清单和备份校验。
2. 运行合并前最小基线检查，记录既有失败，不把基线问题误判为 merge 回归。
3. 将全部治理成果提交为独立中文 checkpoint commit，使每个文件都进入 Git 对象库。
4. 执行 `git merge master`，保留真实 merge ancestry。
5. 按文件职责逐项解决冲突，不使用全局 `ours` 或 `theirs`。

不采用 `stash -u` 作为主要承载方式：本分支文件量大，且历史上发生过未跟踪文件被普通 `mv` 静默覆盖的数据丢失；checkpoint commit 更容易审计、回滚和比较。

## 冲突裁决矩阵

### Shared components、barrels、Storybook 与治理文档

- 以治理分支的组件边界、公共 API、目录归属和 stories 为骨架。
- 吸收 master 新增的业务能力、类型修复、可访问性修复和错误处理。
- master 若恢复已被治理分支收敛的重复组件，不直接恢复旧入口；将新增逻辑移植到现有 shared contract，并同步 stories。
- 所有最终保留的 shared component 必须有 Storybook 契约；组件行为或 props 变化必须同步更新 stories/fixtures。

### App 页面与业务消费者

- 以 master 最新业务流程、接口字段、权限逻辑和 bugfix 为准。
- 以治理分支的 shared component 接入方式为准，避免重新引入 app-local 重复实现。
- 若 master 修改了被抽取组件原实现，先识别新增差异维度，再决定扩展 shared props、保留 app adapter，或判定其不应共享；禁止仅为解冲突复制实现。

### 删除、重命名与目录迁移

- 若治理分支已将旧文件迁移到明确的新 source of truth，保留旧文件删除，并把 master 新逻辑迁到新位置。
- 若删除的是零消费者、重复 wrapper 或多余 barrel，除非 master 引入新的真实消费者，否则继续删除。
- 若治理分支的目标文件只是临时 stub，而 master 存在完整真实实现，优先恢复真实业务逻辑，再适配治理后的组件契约。
- 对每个 modify/delete、rename/add 和 untracked collision 单独检查引用，禁止批量选择一侧。

## 数据安全与可回滚性

- checkpoint 前记录 `git status`、stash 列表、HEAD/master/merge-base，并确认历史 stash 保留。
- checkpoint commit 是本次 merge 的恢复点；不删除既有 stash，不执行 `git reset --hard`、`git checkout --` 或全仓覆盖。
- 合并过程中只处理本次冲突和其直接引发的类型/引用问题，不顺手扩展治理范围。
- 若发现治理成果与 master 新架构根本不兼容，停止该冲突的实现并记录证据，不以高风险猜测继续。

## 验证设计

验证分为四层：

1. **Git 完整性**：无未合并索引项、无冲突标记、merge parent 正确、checkpoint 可达。
2. **静态门禁**：在 `web/` 执行 `pnpm type-check` 与 `pnpm lint`，区分合并前既有失败和本次新增失败。
3. **Storybook 契约**：执行 Storybook build 或仓库现有等价验证；检查所有 shared component 的 stories/fixtures 引用可解析。
4. **运行时 smoke**：启动前端，验证登录、`ops-console`、`cmdb`、`monitor`、`opspilot`、`job`、`alarm` 等代表性入口及关键代理接口。

完成标准：Git 冲突清零；不存在本次合并新增的 lint/type 错误；Storybook 契约可构建；代表性页面不因缺模块、断裂 import 或权限配置而退化为 404/500。

## 非目标

- 不在本次合并中继续发掘新的组件候选。
- 不重写现有组件治理架构。
- 不修改后端业务逻辑，除非仅为验证 master 已有接口契约。
- 不处理与 merge 无关的全仓技术债。
