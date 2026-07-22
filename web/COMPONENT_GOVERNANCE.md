# Web 组件所有权治理

## 约束

`src/components` 只允许两类实现：

1. 被两个及以上真实 app 直接或传递消费的跨 app 组件。
2. 进入 `component-ownership.allowlist.json` 的通用 primitive，类别仅限 Layout、Form、Feedback、Data display、Interaction。

Storybook 是组件行为与变体的契约中心，但 Storybook 引用本身不构成 shared 证据。业务域组件应放在 `src/app/<app>/components`；控制台根壳组件放在 `src/app/(core)/components`。shared 组件禁止反向依赖 `@/app/*`。

## 当前终态

完整机器可读清单见 `component-ownership.manifest.json`。

| 分类 | 数量 | 判定 |
| --- | ---: | --- |
| `shared-cross-app` | 60 | 至少两个真实 app 直接或传递消费 |
| `shared-primitive` | 52 | 当前消费者不足两个，但具有明确 primitive 理由和 contract story |
| `app-local` | 0 | 不允许留在 `src/components` |
| `story-only-review` | 0 | 不允许仅因 Storybook 引用留在 `src/components` |
| `invalid-reverse-dependency` | 0 | shared 禁止依赖 app |
| `unused` | 0 | 无消费者实现必须删除或明确归属 |

白名单共记录 65 个 primitive；其中 13 个当前也已获得跨 app 运行证据，因此 manifest 按优先级将其归为 `shared-cross-app`。所有白名单项均包含 `reason` 和存在的 `contractStory`。

本轮将 `src/components` 从 229 个一级目录收敛到 112 个：114 个业务目录下沉到 app，3 个平行重复实现删除。

## 跨应用对比与决策

### Job

- 候选：`job-*`、文件预览、主机选择、危险规则、脚本编辑、目标选择和 Playbook 弹窗。
- 对比：这些 API 均表达 Job 类型或流程，不存在第二个 app 运行消费者。Host Selection 和 Dangerous Rule 的 Storybook 版本边界更完整；Script Editor 和 Target Controls 的业务版本更接近真实运行态。
- 决策：全部归 `src/app/job/components`。Host Selection 与 Dangerous Rule 采用较完整契约并接回页面；Script Editor 与 Target Controls 保留业务实现，删除 Storybook 平行实现。
- Storybook：`job-family.stories.tsx` 直接引用 app-local 唯一实现。

### Integration / K8s

- 候选：完成态、K8s 三步流程、前置条件提示，以及 catalog、instance、配置和导入壳。
- 对比：`integration-access-complete`、`integration-k8s-configuration-shell`、`integration-step-callout` 已由 Monitor 和 Log 真实页面共同消费；其余契约仍只有 Storybook 证据。
- 决策：前述 3 个保留 shared；其余归 `src/app/monitor/components/integration-contract`，第二个 app 真正接入后才可晋升 shared。`integration-setting-row` 去除业务前缀并收敛为 `form-setting-row` primitive。
- Storybook：Integration/K8s family 分别引用 shared 或 Monitor owner 下的唯一实现。

### Alarm / Monitor / Log

- 候选：`event-*`、`monitor-*`、`log-*`、`k8s-*` 及 `declare-incident`。
- 对比：这些组件只绑定一个业务域的类型、运行时或工作流；跨 family stories 仅用于横向展示，不能证明跨 app 复用。
- 决策：分别归 `src/app/alarm/components`、`src/app/monitor/components`、`src/app/log/components`。通用图表、布局、状态和交互叶子按能力进入 primitive 白名单。
- Storybook：原 family stories 保留，导入改为对应 app-local 路径。

### OpsAnalysis / OpsPilot

- 候选：`ops-analysis-*` 和 `opspilot-*` 的 widgets、配置区、选择器、卡片与工具编辑器。
- 对比：虽然部分展示壳可注入数据，但当前运行语义和类型仍属于单一 app，没有第二个 app 消费证据。
- 决策：分别归 `src/app/ops-analysis/components` 和 `src/app/opspilot/components`；不以“未来可能复用”为由保留 shared。
- Storybook：OpsAnalysis/OpsPilot family 直接验证 app-local 唯一实现。

### CMDB / System Manager / Node Manager / MLOps

- 候选：`cmdb-*`、`custom-reporting-*`、`system-manager-*`、`node-manager-*`、`mlops-*`。
- 对比：组件名称、字段模型、接口和操作流程均绑定对应 app；Storybook 中的多场景展示不改变所有权。
- 决策：全部归各自 `src/app/<app>/components`。
- Storybook：保留业务 family 契约，导入切换到 app-local 唯一实现。

### 控制台根壳

- 候选：`top-menu`、`user-preferences` 和旧 `user-info`。
- 对比：它们服务根 layout，而不是多个业务 app。旧 `user-info` 与 `top-menu/user-info` 重复，且反向依赖 System Manager。
- 决策：`top-menu`、`user-preferences` 归 `src/app/(core)/components`；删除旧 `src/components/user-info`，以 `top-menu/user-info` 为唯一实现。
- Storybook：Layout、TopMenu、User Profile stories 直接引用根壳实现。

## Primitive 白名单规则

- 白名单按能力登记，不按目录前缀登记。
- 带 `job-`、`cmdb-`、`monitor-`、`opspilot-` 等业务前缀的组件不得进入 primitive 白名单。
- 每条必须包含：
  - `component`：`src/components` 一级目录名。
  - `reason`：不依赖具体业务语义的理由。
  - `contractStory`：Storybook 唯一契约文件。
- 当 primitive 获得两个以上 app 消费后，manifest 自动优先归为 `shared-cross-app`，无需删除白名单说明。

## 门禁

```bash
pnpm audit:component-ownership
pnpm check:component-ownership
pnpm type-check
pnpm build-storybook
```

新增目录若为单 app、story-only、unused 或反向依赖 app，`check:component-ownership` 必须失败。业务组件晋升 shared 前必须先完成至少两个 app 的真实迁移，并同步更新 Storybook contract。
