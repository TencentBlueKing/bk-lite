# Web 组件所有权全量回收设计

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
