# Web 组件治理分支合并 Master 实施计划

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
