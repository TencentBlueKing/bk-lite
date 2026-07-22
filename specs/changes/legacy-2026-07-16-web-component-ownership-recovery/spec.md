# Historical Superpowers change: 2026-07-16-web-component-ownership-recovery

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-16-web-component-ownership-recovery.md

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

## specs: 2026-07-16-web-component-ownership-recovery-design.md

## 背景

当前 `web/src/components` 同时承载了设计系统基础组件、真实跨应用共享组件、单应用业务组件和仅供 Storybook 展示的平行实现。初步直接引用扫描显示，229 个组件目录中只有 25 个被两个及以上 app 直接消费，22 个仅被一个 app 消费，182 个没有 app 直接消费，其中 172 个仅由 stories 引用，另有 7 个目录反向依赖 `@/app/*`。

直接引用数不是最终判定：组件可能通过另一个 shared component 被业务间接消费。因此本次治理先建立传递依赖闭包，再决定所有权，禁止依据目录名或单层 `rg` 结果直接批量迁移。

## 目标

将 `web/src/components` 收敛为两类唯一真实来源：

1. 被两个及以上真实 app 消费的跨应用共享组件。
2. 经白名单确认的设计系统基础能力，包括布局、表单基础控件、反馈、数据展示和基础交互 primitives。

单应用业务组件归还 `web/src/app/<app>/components`。Storybook 继续作为行为与变体契约中心，但不再决定组件的目录所有权；stories 可以直接引用 app-local 组件。

## 所有权判定模型

审计工具为每个 `src/components/<name>` 生成以下证据：

- 直接 app 消费者及文件列表。
- 通过其他 shared components 到达的传递 app 消费者。
- stories 消费者及 story 标题。
- 对 `@/app/*` 的反向依赖。
- 同名、近似名或相同实现的 app-local 候选。
- 组件 API 中的业务域词汇和业务类型依赖。
- 当前 Storybook 构建状态。

判定顺序：

1. 反向依赖 app 或绑定单一业务类型：归属对应 app，除非先完成真正的依赖反转并已有跨 app 消费证据。
2. 两个及以上 app 的传递消费者：保留 shared，并检查 API 是否已经收敛。
3. 设计系统 primitive 白名单：允许在消费者不足两个时保留 shared。
4. 单 app 消费：迁回该 app。
5. 仅 stories 消费：进入“平行实现裁决”，不自动保留。
6. 无任何消费者：删除，除非存在已批准但尚未接入的明确迁移任务。

## Primitive 白名单

白名单按能力而不是目录前缀维护，仅接受以下类别：

- Layout：通用页面、抽屉、弹窗和分栏布局骨架。
- Form：不包含业务字段语义的输入、校验、字段编排能力。
- Feedback：通用空态、错误态、加载态、确认和通知展示。
- Data display：通用表格、列表、标签、截断、图例和格式化展示。
- Interaction：搜索、选择、拖拽、复制、上传等通用交互原语。

带有 `job-`、`cmdb-`、`monitor-`、`opspilot-` 等业务域前缀的组件默认不属于 primitive；保留 shared 必须提供跨 app 消费证据，不能仅凭“未来可能复用”。

## Story-only 平行实现裁决

对于只有 stories 使用、业务仍有 app-local 实现的组件，逐个比较以下事实：

- 功能与交互覆盖度。
- API 是否稳定、是否表达业务语义。
- 真实业务依赖是否可注入。
- stories 是否覆盖业务现有变体。
- 迁移成本和回归风险。

默认优先保留业务真实实现，并让 Storybook 直接引用它。若 Storybook 版本明显更完整且边界更清晰，则先迁移真实业务调用方，再删除 app-local 重复实现。没有业务价值的 demo-only 平行实现及其 stories 直接删除。

任何裁决完成后只能保留一个实现源；禁止长期维护“业务一套、Storybook 一套”。

## 分批迁移顺序

### 第一层：审计基础设施

- 新增可重复运行的 ownership 审计脚本和机器可读清单。
- 建立 primitive 白名单和允许的例外说明。
- 为直接/传递消费者、反向依赖和 story-only 分类编写测试。

### 第二层：确定性错误

- 处理反向依赖 `@/app/*` 的 shared 目录。
- 删除无业务消费者、无间接消费者且无保留理由的 demo-only 实现。
- 修正 app 已有真实实现、shared 仅为平行 story 壳的目录。

### 第三层：按业务域回收

按 Job、Integration、Event/Alarm、Monitor、OpsAnalysis、OpsPilot、CMDB、System Manager、Node Manager、MLOps、Log 的顺序处理。每个业务域独立形成可验证批次，先决定唯一实现，再迁移引用和 stories。

### 第四层：Shared 收敛

- 复核剩余 shared 组件的跨 app API。
- 合并重复 primitive，移除业务域泄漏。
- 更新治理文档，确保审计脚本对新增违规返回非零退出码。

## 安全约束

- 禁止使用会静默覆盖目标文件的批量 `mv`。
- 迁移前确认目标路径不存在；优先使用可审查的 Git rename。
- 不删除仍有直接或传递业务消费者的实现。
- 不以类型声明、转发壳或复制业务类型制造伪共享。
- 仅修改当前批次相关文件，禁止全仓格式化。
- 当前 worktree 中已有未提交修复必须保留，设计文档和后续批次分别提交。

## 验证策略

每个迁移批次必须完成：

1. ownership 审计脚本针对该域无未解释违规。
2. `pnpm type-check` 通过。
3. 受影响 stories 可编译；阶段性批次运行针对性 Storybook，最终运行完整 `storybook build`。
4. 受影响源码定向 ESLint 通过。
5. 至少一个真实业务页面完成运行态冒烟。
6. `git diff --check` 通过，且不存在意外删除或覆盖。

全量完成标准：

- 所有 `src/components` 目录均有跨 app 消费证据或 primitive 白名单理由。
- `src/components` 对 `@/app/*` 的反向依赖为零。
- story-only 平行业务实现为零。
- 单 app 业务组件全部归还对应 app。
- Storybook、type-check 和相关业务页面验证通过。

## 输出

治理结束后提供：

- 全量组件 ownership 清单及判定理由。
- 每个业务域的候选、跨应用对比、最终归属和迁移路径。
- 保留 shared 的 API/变体依据。
- 删除或下沉组件的 Storybook 更新记录。
- 剩余例外及其明确到期条件。
