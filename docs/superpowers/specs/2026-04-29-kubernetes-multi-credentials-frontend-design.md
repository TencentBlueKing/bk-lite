# Kubernetes 多凭据前端改造设计

## 背景

当前后端已经将 Kubernetes 工具参数模型调整为仅使用结构化 `kubernetes_instances` 数组，不再依赖 `kubernetes_default_instance_id`。Web 前端虽然已有 Kubernetes 多实例编辑器骨架，但保存逻辑仍会写入 `kubernetes_default_instance_id`，其交互语义也仍然带有“默认实例”残留。

本次改造目标是让前端与后端参数契约保持一致，并与 `mysql`、`redis` 等工具的多实例编辑体验对齐。

## 目标

- 在 OpsPilot 工具配置前端中，将 Kubernetes 凭据配置统一为多实例列表编辑模式。
- 移除前端对 `kubernetes_default_instance_id` 的写入和依赖。
- 保持对旧配置 `kubeconfig_data` 的读取兼容，避免历史配置立即失效。
- 维持与现有数据库类工具一致的交互模式：左侧实例列表，右侧实例详情，单实例连通性测试。

## 非目标

- 不新增“默认实例”选择器或兼容隐藏字段。
- 不改造后端接口结构。
- 不增加批量测试、批量导入、拖拽排序等增强能力。
- 不重做整体工具配置页面布局。

## 现状

### 相关文件

- `web/src/app/opspilot/components/skill/toolSelector.tsx`
- `web/src/app/opspilot/components/skill/kubernetesToolEditor.tsx`

### 当前行为

- `parseKubernetesToolConfig()` 已支持优先读取 `kubernetes_instances`。
- 当只有旧字段 `kubeconfig_data` 时，前端会回退映射为单实例配置。
- `serializeKubernetesToolConfig()` 当前仍会输出：
  - `kubernetes_instances`
  - `kubernetes_default_instance_id`
- `kubernetesToolEditor.tsx` 已具备多实例列表和实例详情编辑 UI。

## 设计决策

### 1. 统一参数语义为“实例列表”

Kubernetes 前端配置只维护 `kubernetes_instances`。前端不再表达“默认实例”概念。

运行时语义由后端负责：

- 用户明确指定 `instance_id` 或 `instance_name` 时，按指定实例执行。
- 用户未指定时，对全部实例执行或聚合。

### 2. 保持现有编辑器结构

沿用现有 `kubernetesToolEditor.tsx` 的布局，不重做视觉结构：

- 左侧：实例列表
- 右侧：当前实例详情
- 底部动作：测试当前实例连接

这与 `mysqlToolEditor.tsx` 的交互方式一致，降低维护成本和学习成本。

### 3. 读取兼容，写入收敛

为了兼容历史配置，前端读取时仍支持：

- 新格式：`kubernetes_instances`
- 旧格式：`kubeconfig_data`

但保存时统一只写新格式：

- `kubernetes_instances`

不再写入 `kubernetes_default_instance_id`。

这样用户只要打开并保存一次配置，即可完成前端侧迁移。

## 具体改动

### A. `toolSelector.tsx`

#### A1. Kubernetes 常量调整

- 删除 `KUBERNETES_DEFAULT_INSTANCE_ID_KEY`
- 保留 `KUBERNETES_INSTANCES_KEY`

#### A2. 解析逻辑

`parseKubernetesToolConfig()` 保持当前整体策略：

1. 优先解析 `kubernetes_instances`
2. 若不存在，则尝试从旧字段 `kubeconfig_data` 构造单实例
3. 若仍无配置，则创建默认空白实例

#### A3. 序列化逻辑

`serializeKubernetesToolConfig()` 调整为：

- 去除 `testStatus`
- 仅返回 `[{ key: 'kubernetes_instances', value: JSON.stringify(instances) }]`

#### A4. 保存前校验

Kubernetes 保存校验与 `mysql` 风格保持一致：

- 实例列表不能为空
- 每个实例 `name` 必填
- `name` 必须唯一
- 每个实例 `kubeconfig_data` 必填

错误提示沿用当前国际化方式，补齐缺失文案键。

### B. `kubernetesToolEditor.tsx`

#### B1. 交互语义

- 不展示默认实例相关文案或控件
- 继续支持新增、选择、删除实例
- 继续支持对当前选中实例进行连通性测试

#### B2. 删除后的选中策略

删除当前实例后，前端应自动选中剩余实例中的一个；若已删空，则选中置空。

这样可避免删除当前项后右侧详情面板状态不一致。

#### B3. 展示一致性

列表摘要继续显示：

- 实例名称
- kubeconfig 首行预览

不额外增加默认标签、主实例标识或排序标识。

### C. 国际化文案

检查并补齐 `web/src/app/opspilot/locales/zh.json`、`en.json` 中 Kubernetes 配置所需文案，重点包括：

- 无实例提示
- 实例名必填
- 实例名重复
- kubeconfig 必填
- 选择实例提示

## 数据流

### 打开编辑弹窗

1. `openEditModal()` 识别 Kubernetes 工具
2. 调用 `parseKubernetesToolConfig(tool.kwargs)`
3. 将结果写入 `kubernetesInstances`
4. 默认选中第一条实例

### 编辑过程中

1. 用户编辑名称或 kubeconfig
2. `onChange()` 更新当前实例状态
3. 当前实例 `testStatus` 可在字段变化后重置为 `untested`

### 保存时

1. 执行前端校验
2. 对实例字段做 `trim`
3. 调用 `serializeKubernetesToolConfig()`
4. 将新 `kwargs` 写回 `selectedTools`

## 错误处理

- 当实例为空时，阻止保存并提示用户先添加实例。
- 当实例名为空或重复时，阻止保存。
- 当 kubeconfig 为空时，阻止保存。
- 当测试连接时没有选中实例，直接返回，不发请求。

## 测试与验证

本次以前端最小验证为主：

- `web` 下运行 `pnpm lint`
- `web` 下运行 `pnpm type-check`

手工验证重点：

1. 打开 Kubernetes 工具配置，新增多个实例并保存。
2. 重新打开编辑弹窗，确认多实例被正确回显。
3. 历史仅含 `kubeconfig_data` 的配置可被读出并转换为单实例。
4. 保存后不再写入 `kubernetes_default_instance_id`。
5. 删除当前实例后，右侧面板选中状态正常切换。

## 风险与控制

### 风险

- 历史数据可能仍包含旧字段，若解析逻辑处理不完整，可能导致回显异常。
- 文案键缺失可能引发页面展示退化。
- 删除实例后的选中状态若未处理好，可能出现空引用问题。

### 控制措施

- 保留旧字段读取兼容。
- 只做最小行为改动，不重构公共工具选择器框架。
- 用 lint 和 type-check 兜底检查类型与常见前端错误。

## 预期结果

完成后，Kubernetes 工具前端配置将与后端参数契约保持一致，用户可在 UI 中维护多个 kubeconfig 实例，且不再暴露或保存“默认实例”概念。
