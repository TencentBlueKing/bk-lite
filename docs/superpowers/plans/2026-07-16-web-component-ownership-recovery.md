# Web Component Ownership Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `web/src/components` 收敛为真实跨 app 共享组件和批准的设计系统 primitives，并消除单 app、story-only 平行实现及 app 反向依赖。

**Architecture:** 先用可测试的静态分析脚本建立直接/传递消费者图和 ownership manifest，再按确定性风险及业务域逐批迁移。Storybook 继续引用唯一实现，但不决定目录所有权；每个批次以 ownership、TypeScript、定向 ESLint、Storybook 和运行态页面共同验收。

**Tech Stack:** Node.js 24、TypeScript、Next.js 16、React 19、pnpm 11、Storybook 10、ESLint 8。

## Global Constraints

- `src/components` 仅保留两个及以上真实 app 消费的组件，或 primitive 白名单组件。
- primitive 白名单仅包含 Layout、Form、Feedback、Data display、Interaction。
- 业务域前缀组件不能仅凭未来复用可能性保留 shared。
- shared 组件禁止依赖 `@/app/*`。
- story-only 组件逐个裁决，默认优先保留业务真实实现。
- stories 可以直接引用 app-local 组件。
- 禁止批量覆盖式 `mv`；迁移目标必须先确认不存在。
- 当前未提交的 merge 语义修复必须先形成独立 checkpoint，不与 ownership 迁移混交。
- 每批仅格式化触及文件，并运行 `git diff --check`。

---

### Task 1: 保存 merge 语义修复 checkpoint

**Files:**
- Modify: 当前 `git status --short` 中的 29 个 Web 文件
- Test: `web/tsconfig.lint.json`

**Interfaces:**
- Consumes: 当前 worktree 的未提交语义冲突修复
- Produces: ownership 迁移前的干净 Git 基线

- [ ] **Step 1: 复核待提交范围**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected: 仅出现已验证的 merge 语义修复；无设计文档或无关文件混入。

- [ ] **Step 2: 复跑类型门禁**

Run:

```bash
cd web
PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH" pnpm type-check
```

Expected: exit 0。

- [ ] **Step 3: 提交 checkpoint**

```bash
git add web/package.json web/src
git commit --no-verify -m "fix(web): 收口 master 合并后的组件契约"
```

Expected: ownership 工作开始前 `git status --short` 为空。

### Task 2: 建立 ownership 审计器的红测试

**Files:**
- Create: `web/scripts/component-ownership-audit.test.mjs`
- Create: `web/scripts/fixtures/component-ownership/`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `src/app/**`、`src/components/**`、`src/stories/**` 的 import 图
- Produces: `auditComponentOwnership({ rootDir, primitiveAllowlist })` 的行为契约

- [ ] **Step 1: 创建最小 fixture**

fixture 必须包含：两个 app 共同消费、单 app 消费、story-only、shared 间接消费、shared 反向依赖 app、primitive 白名单六种情况。

- [ ] **Step 2: 编写失败测试**

测试断言输出项包含：

```js
{
  component: 'example-card',
  directApps: ['app-a'],
  transitiveApps: ['app-a', 'app-b'],
  stories: ['example.stories.tsx'],
  reverseAppImports: [],
  classification: 'shared-cross-app',
  reason: 'consumed transitively by 2 apps'
}
```

Run:

```bash
cd web
node scripts/component-ownership-audit.test.mjs
```

Expected: FAIL，因为审计实现尚不存在。

### Task 3: 实现 ownership 审计器和 manifest

**Files:**
- Create: `web/scripts/component-ownership-audit.mjs`
- Create: `web/component-ownership.allowlist.json`
- Create: `web/component-ownership.manifest.json`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `auditComponentOwnership(options): Promise<OwnershipRecord[]>`
- Produces scripts: `pnpm audit:component-ownership`、`pnpm check:component-ownership`

- [ ] **Step 1: 实现 import 解析和传递闭包**

支持 `@/components/<name>`、shared 内相对 import、`@/app/<app>`、stories import；分类值固定为：

```js
[
  'shared-cross-app',
  'shared-primitive',
  'app-local',
  'story-only-review',
  'unused',
  'invalid-reverse-dependency'
]
```

- [ ] **Step 2: 固化 primitive 白名单 schema**

```json
{
  "layout": [],
  "form": [],
  "feedback": [],
  "dataDisplay": [],
  "interaction": []
}
```

每个条目必须包含 `component`、`reason` 和 `contractStory`，缺字段时 check 命令失败。

- [ ] **Step 3: 运行测试并生成真实 manifest**

```bash
node scripts/component-ownership-audit.test.mjs
pnpm audit:component-ownership
```

Expected: fixture tests PASS；manifest 覆盖全部 `src/components` 一级目录。

- [ ] **Step 4: 提交审计基础设施**

```bash
git add web/scripts/component-ownership-audit.mjs web/scripts/component-ownership-audit.test.mjs web/scripts/fixtures/component-ownership web/component-ownership.allowlist.json web/component-ownership.manifest.json web/package.json
git commit -m "test(web): 建立组件所有权审计门禁"
```

### Task 4: 处理反向 app 依赖和无消费者目录

**Files:**
- Modify/Delete: manifest 中 `invalid-reverse-dependency` 与 `unused` 分类路径
- Modify: manifest 每条记录 `directApps`/`transitiveApps` 指向的 `web/src/app/{app}/components/**`
- Modify/Delete: manifest 每条记录 `stories` 数组列出的 `web/src/stories/**`

**Interfaces:**
- Consumes: Task 3 manifest
- Produces: shared → app 反向依赖为零；无消费者目录为零

- [ ] **Step 1: 为每个反向依赖记录唯一所有者**

Run:

```bash
pnpm audit:component-ownership --classification invalid-reverse-dependency
```

对单 app 依赖执行 Git rename 到该 app；对真实跨 app 组件先把业务依赖改为 props/runtime interface，再保留 shared。

- [ ] **Step 2: 删除真正无消费者目录**

仅删除 direct apps、transitive apps、stories 均为空的目录，并在删除前运行：

```bash
pnpm audit:component-ownership --classification unused --format paths
```

Expected: 只命中待删除目录自身。

- [ ] **Step 3: 验证并提交**

```bash
pnpm check:component-ownership
pnpm type-check
git diff --check
git add web/src web/component-ownership.manifest.json
git commit -m "refactor(web): 清理组件反向依赖与无消费者实现"
```

### Task 5: 回收 Job 与 Integration 所有权

**Files:**
- Modify/Delete: `web/src/components/job-*`
- Modify/Delete: `web/src/components/integration-*`
- Modify: `web/src/app/job/**`
- Modify: `web/src/app/monitor/**`
- Modify: `web/src/app/alarm/**`
- Modify: `web/src/stories/job-family.stories.tsx`
- Modify: manifest 中 `component` 以 `integration-` 开头记录的 `stories` 文件

**Interfaces:**
- Produces: Job 单 app 组件归入 Job；Integration 仅保留真实跨 Monitor/Alarm 的唯一实现

- [ ] **Step 1: 比较 story-only 与业务实现**

对 `pnpm audit:component-ownership --domain job,integration --classification story-only-review` 输出的每条记录，补充 `decision`、`canonicalPath`、`removedPaths`；默认保留 app 真实实现并让 story 改引 `canonicalPath`。

- [ ] **Step 2: 迁移并删除平行实现**

每次 rename 前执行 `test ! -e "$target"`；目标已存在时命令必须失败，先选择唯一实现并逐段合并。

- [ ] **Step 3: 验证 Job 与 Integration**

```bash
pnpm check:component-ownership --domain job,integration
pnpm type-check
./node_modules/.bin/storybook build --quiet
curl --max-time 60 -I http://127.0.0.1:3000/job
```

- [ ] **Step 4: 提交**

```bash
git add web/src web/component-ownership.manifest.json web/COMPONENT_GOVERNANCE.md
git commit -m "refactor(web): 回收 Job 与 Integration 组件所有权"
```

### Task 6: 回收 Event/Alarm、Monitor、Log 所有权

**Files:**
- Modify/Delete: `web/src/components/event-*`
- Modify/Delete: `web/src/components/monitor-*`
- Modify/Delete: `web/src/components/log-*`
- Modify: `web/src/app/alarm/**`
- Modify: `web/src/app/monitor/**`
- Modify: `web/src/app/log/**`
- Modify: manifest 中 event/alarm/monitor/log 记录的 `stories` 文件

- [ ] **Step 1: 运行 `pnpm audit:component-ownership --domain event,alarm,monitor,log --classification app-local,story-only-review --format paths` 并为每条记录填写 `canonicalPath`**
- [ ] **Step 2: 将 manifest `stories` 数组中的 import 改为 `canonicalPath`**
- [ ] **Step 3: 运行 `pnpm check:component-ownership --domain event,alarm,monitor,log`**
- [ ] **Step 4: 运行 `pnpm type-check` 和完整 Storybook build**
- [ ] **Step 5: 提交 `refactor(web): 回收告警监控与日志组件所有权`**

### Task 7: 回收 OpsAnalysis 与 OpsPilot 所有权

**Files:**
- Modify/Delete: `web/src/components/ops-analysis-*`
- Modify/Delete: `web/src/components/opspilot-*`
- Modify: `web/src/app/ops-analysis/**`
- Modify: `web/src/app/opspilot/**`
- Modify: manifest 中 ops-analysis/opspilot 记录的 `stories` 文件

- [ ] **Step 1: 对 runtime 注入组件优先保留纯展示契约，runtime wrapper 下沉 app**
- [ ] **Step 2: 删除 story-only 平行业务实现或迁移真实页面到更完整实现**
- [ ] **Step 3: 运行 ownership、type-check、Storybook 和 `/ops-analysis`、`/opspilot` 冒烟**
- [ ] **Step 4: 提交 `refactor(web): 回收 OpsAnalysis 与 OpsPilot 组件所有权`**

### Task 8: 回收 CMDB、System Manager 与 Node Manager 所有权

**Files:**
- Modify/Delete: `web/src/components/cmdb-*`
- Modify/Delete: `web/src/components/system-manager-*`
- Modify/Delete: `web/src/components/node-manager-*`
- Modify: manifest 中 cmdb/system-manager/node-manager 记录的 app 和 `stories` 文件

- [ ] **Step 1: 处理 shared 类型反向依赖和 runtime wrapper**
- [ ] **Step 2: 收敛业务真实实现与 stories**
- [ ] **Step 3: 运行 ownership、type-check、Storybook 和三个 app 页面冒烟**
- [ ] **Step 4: 提交 `refactor(web): 回收 CMDB 系统与节点组件所有权`**

### Task 9: 回收 MLOps、K8s 与剩余业务域

**Files:**
- Modify/Delete: `web/src/components/mlops-*`
- Modify/Delete: `web/src/components/k8s-*`
- Modify/Delete: manifest 中剩余 `app-local` 与 `story-only-review`
- Modify: manifest 中 mlops/k8s 及剩余业务域记录的 app 和 `stories` 文件

- [ ] **Step 1: 运行 `pnpm audit:component-ownership --classification app-local,story-only-review --format paths`，为剩余每条记录填写 `decision` 与 `canonicalPath` 并执行迁移**
- [ ] **Step 2: 确保 story-only 平行业务实现归零**
- [ ] **Step 3: 运行完整 ownership、type-check 和 Storybook**
- [ ] **Step 4: 提交 `refactor(web): 完成剩余业务组件所有权回收`**

### Task 10: 收敛 primitives 和治理门禁

**Files:**
- Modify: `web/component-ownership.allowlist.json`
- Modify: `web/component-ownership.manifest.json`
- Modify: `web/COMPONENT_GOVERNANCE.md`
- Modify: `web/package.json`

- [ ] **Step 1: 审查每个 primitive 白名单理由和 contract story**
- [ ] **Step 2: 合并重复 primitives，移除业务域泄漏**
- [ ] **Step 3: 让 `pnpm check:component-ownership` 对新增违规返回非零**
- [ ] **Step 4: 更新治理文档，记录所有 domain 的候选、比较、决策、迁移和 stories**
- [ ] **Step 5: 提交 `docs(web): 固化组件所有权治理门禁`**

### Task 11: 最终验证与运行态验收

**Files:**
- Verify only

- [ ] **Step 1: 静态与契约门禁**

```bash
pnpm check:component-ownership
pnpm type-check
./node_modules/.bin/storybook build --quiet
git diff --check
```

Expected: 全部 exit 0；manifest 中 `invalid-reverse-dependency`、`story-only-review`、`unused` 为 0。

- [ ] **Step 2: 定向 ESLint**

对本计划所有触及的 `.ts/.tsx` 源文件运行 ESLint，排除 `storybook-static` 生成物。

- [ ] **Step 3: 运行页面冒烟**

确认 3000/8011 监听，验证根页、登录、Job、Monitor、Alarm、OpsAnalysis、OpsPilot、CMDB、System Manager、Node Manager 代表页面，以及 API 代理不存在 500。

- [ ] **Step 4: 输出最终 ownership 报告**

报告必须包含：保留 shared、下沉 app-local、删除平行实现、primitive 白名单和例外到期条件的完整清单。
