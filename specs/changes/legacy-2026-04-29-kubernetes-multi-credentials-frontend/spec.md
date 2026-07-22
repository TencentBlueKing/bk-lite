# Historical Superpowers change: 2026-04-29-kubernetes-multi-credentials-frontend

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-04-29-kubernetes-multi-credentials-frontend.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the OpsPilot Kubernetes tool editor save and validate multi-instance kubeconfig credentials using only `kubernetes_instances`, with no default-instance frontend semantics.

**Architecture:** Keep the existing two-panel Kubernetes editor UI and align its parsing, validation, and serialization behavior with the existing multi-instance tool editors such as MySQL. Preserve backward-compatible reads from legacy `kubeconfig_data`, but converge all saves to the array-based contract.

**Tech Stack:** Next.js, React 19, TypeScript, Ant Design, existing OpsPilot i18n JSON locales.

---

### Task 1: Update Kubernetes tool parsing and serialization

**Files:**
- Modify: `web/src/app/opspilot/components/skill/toolSelector.tsx`

- [ ] **Step 1: Add the failing behavior check in code review form**

Confirm the current Kubernetes serializer still emits the removed compatibility field:

```ts
return [
  { key: KUBERNETES_INSTANCES_KEY, value: JSON.stringify(normalized) },
  { key: KUBERNETES_DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
];
```

Expected: the file still writes `kubernetes_default_instance_id`, which no longer matches the backend contract.

- [ ] **Step 2: Remove the obsolete default-instance constant and serializer output**

Change the Kubernetes serializer to only emit the array payload:

```ts
const serializeKubernetesToolConfig = (instances: KubernetesInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((instance) => {
    const copy = { ...instance };
    delete copy.testStatus;
    return copy;
  });

  return [{ key: KUBERNETES_INSTANCES_KEY, value: JSON.stringify(normalized) }];
};
```

- [ ] **Step 3: Keep legacy parsing compatibility**

Ensure the parser still supports both:

```ts
const instancesValue = kwargsMap.get(KUBERNETES_INSTANCES_KEY);
const parsedInstances = parseKubernetesInstancesValue(instancesValue);
```

and legacy fallback:

```ts
const hasLegacyConfig = ['kubeconfig_data'].some((key) => kwargsMap.has(key));
```

Expected: old single-kubeconfig records still open correctly in the editor.

### Task 2: Add Kubernetes save validation matching other multi-instance tools

**Files:**
- Modify: `web/src/app/opspilot/components/skill/toolSelector.tsx`

- [ ] **Step 1: Add Kubernetes validation branch in `handleEditModalOk()`**

Implement the same shape used by MySQL and Redis, adapted for kubeconfig:

```ts
if (isKubernetesTool(editingTool)) {
  const trimmedNames = kubernetesInstances.map((instance) => instance.name.trim()).filter(Boolean);
  if (kubernetesInstances.length === 0) {
    message.error(t('tool.kubernetes.noInstances'));
    return;
  }
  if (trimmedNames.length !== kubernetesInstances.length) {
    message.error(t('tool.kubernetes.instanceNameRequired'));
    return;
  }
  if (new Set(trimmedNames).size !== trimmedNames.length) {
    message.error(t('tool.kubernetes.duplicateInstanceName'));
    return;
  }
  if (kubernetesInstances.some((instance) => !instance.kubeconfig_data.trim())) {
    message.error(t('tool.kubernetes.kubeconfigDataRequired'));
    return;
  }
}
```

- [ ] **Step 2: Save trimmed instance values back into selected tools**

Persist normalized data in the same branch:

```ts
const updatedTool = {
  ...editingTool,
  kwargs: serializeKubernetesToolConfig(
    kubernetesInstances.map((instance) => ({
      ...instance,
      name: instance.name.trim(),
      kubeconfig_data: instance.kubeconfig_data.trim(),
    })),
  ),
};
```

- [ ] **Step 3: Close modal and clear editor state after save**

Use the same completion flow as the other tool branches:

```ts
setSelectedTools(updatedSelectedTools);
onChange(updatedSelectedTools);
setEditModalVisible(false);
setEditingTool(null);
return;
```

### Task 3: Refine Kubernetes editor behavior and locale coverage

**Files:**
- Modify: `web/src/app/opspilot/components/skill/kubernetesToolEditor.tsx`
- Modify: `web/src/app/opspilot/locales/zh.json`
- Modify: `web/src/app/opspilot/locales/en.json`

- [ ] **Step 1: Keep editor semantics focused on instance list only**

Do not add any default-instance selector or badge. Keep the component API unchanged and preserve the two-panel layout.

- [ ] **Step 2: Confirm per-instance edits reset test status**

Retain the current instance change behavior in `toolSelector.tsx`:

```ts
instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
```

Expected: editing kubeconfig or instance name invalidates previous test status.

- [ ] **Step 3: Add missing locale keys used by Kubernetes validation and editor states**

Ensure both locale files contain keys for:

```json
"noInstances": "...",
"instanceNameRequired": "...",
"duplicateInstanceName": "...",
"kubeconfigDataRequired": "...",
"selectInstance": "..."
```

Expected: no raw i18n keys appear in the UI during save or empty states.

### Task 4: Verify the frontend changes

**Files:**
- Verify: `web/src/app/opspilot/components/skill/toolSelector.tsx`
- Verify: `web/src/app/opspilot/components/skill/kubernetesToolEditor.tsx`
- Verify: `web/src/app/opspilot/locales/zh.json`
- Verify: `web/src/app/opspilot/locales/en.json`

- [ ] **Step 1: Run lint**

Run: `pnpm lint`

Expected: no ESLint errors caused by the Kubernetes frontend changes.

- [ ] **Step 2: Run type-check**

Run: `pnpm type-check`

Expected: TypeScript passes without type errors caused by the Kubernetes frontend changes.

- [ ] **Step 3: Re-read the changed code against the spec**

Confirm the implementation satisfies all of the following:

```md
- saves only `kubernetes_instances`
- still reads legacy `kubeconfig_data`
- validates non-empty unique names
- validates non-empty kubeconfig data
- keeps single-instance connection testing
- exposes no default-instance frontend semantics
```

## specs: 2026-04-29-kubernetes-multi-credentials-frontend-design.md

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
