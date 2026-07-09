# 主机（Telegraf）实例名称默认值 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 主机（Telegraf）选择采集节点时，将节点真实名称填入可继续编辑的实例名称字段。

**Architecture:** 将“从下拉选项读取字段并更新目标列”实现为纯函数，由通用表格渲染器调用；主机（Telegraf）通过 JSON 声明启用，其他插件保持原行为。纯函数用现有 `tsx` 脚本测试方式验证，避免把插件判断写死在页面组件中。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design、pnpm、tsx。

## Global Constraints

- 仅主机（Telegraf）启用该默认值行为。
- 自动填入后实例名称仍可编辑。
- 重新选择节点时刷新默认值；清空或无法解析节点时不覆盖现值。
- 实例名称取节点真实 `name`，不取包含 IP 的展示 `label`。
- 提交参数与后端数据结构不变。
- 新功能遵循 TDD，先红后绿。

---

### Task 1: 声明式下拉选项字段联动

**Files:**
- Create: `web/src/app/monitor/hooks/integration/tableChangeHandler.ts`
- Create: `web/scripts/monitor-table-change-handler-test.ts`
- Modify: `web/src/app/monitor/hooks/integration/useConfigRenderer.tsx`
- Modify: `server/apps/monitor/support-files/plugins/Telegraf/host/os/UI.json`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: 当前列值、当前行、列选项以及 JSON 中的 `change_handler`。
- Produces: `applyTableChangeHandler(row, value, options, changeHandler): Record<string, any>`；返回更新后的行，找不到有效选项值时返回不覆盖目标字段的行。

- [ ] **Step 1: 写失败测试**

在 `web/scripts/monitor-table-change-handler-test.ts` 中用 `node:assert/strict` 覆盖：

```ts
import assert from 'node:assert/strict';
import { applyTableChangeHandler } from '../src/app/monitor/hooks/integration/tableChangeHandler';

const options = [
  { value: 'node-1', name: '生产节点 A', label: '生产节点 A (10.0.0.1)' },
  { value: 'node-2', name: '生产节点 B', label: '生产节点 B (10.0.0.2)' }
];
const handler = {
  type: 'option_field',
  source_field: 'name',
  target_field: 'instance_name'
};

assert.equal(
  applyTableChangeHandler(
    { instance_name: '自定义名称' },
    'node-1',
    options,
    handler
  ).instance_name,
  '生产节点 A'
);
assert.equal(
  applyTableChangeHandler(
    { instance_name: '生产节点 A' },
    'node-2',
    options,
    handler
  ).instance_name,
  '生产节点 B'
);
assert.equal(
  applyTableChangeHandler(
    { instance_name: '保留名称' },
    undefined,
    options,
    handler
  ).instance_name,
  '保留名称'
);
assert.equal(
  applyTableChangeHandler(
    { instance_name: '保留名称' },
    'missing',
    options,
    handler
  ).instance_name,
  '保留名称'
);
assert.deepEqual(
  applyTableChangeHandler({ host: '' }, '10.0.0.1', [], {
    type: 'simple',
    source_fields: ['host'],
    target_field: 'instance_name'
  }),
  { host: '', instance_name: '' }
);

console.log('monitor table change handler tests passed');
```

并在 `web/package.json` 增加：

```json
"test:monitor-table-change-handler": "pnpm exec tsx scripts/monitor-table-change-handler-test.ts"
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `cd web && pnpm test:monitor-table-change-handler`

Expected: FAIL，提示 `tableChangeHandler` 模块不存在。

- [ ] **Step 3: 实现最小纯函数并接入渲染器**

在 `tableChangeHandler.ts` 定义处理器类型和 `applyTableChangeHandler`：

```ts
export const applyTableChangeHandler = (
  row: Record<string, any>,
  value: any,
  options: Record<string, any>[],
  handler?: Record<string, any>
) => {
  if (!handler) return row;
  if (handler.type === 'simple') {
    const sourceValue = handler.source_fields?.[0]
      ? row[handler.source_fields[0]]
      : value;
    return { ...row, [handler.target_field]: sourceValue };
  }
  if (handler.type === 'combine') {
    const sourceValues = (handler.source_fields || []).map(
      (field: string) => row[field] || ''
    );
    return {
      ...row,
      [handler.target_field]: sourceValues.join(handler.separator || ':')
    };
  }
  if (handler.type === 'option_field') {
    const option = options.find((item) => item.value === value);
    const sourceValue = option?.[handler.source_field];
    if (
      sourceValue === undefined ||
      sourceValue === null ||
      sourceValue === ''
    ) {
      return row;
    }
    return { ...row, [handler.target_field]: sourceValue };
  }
  return row;
};
```

`useConfigRenderer.tsx` 的 `handleChange` 先写入当前字段与校验结果，再调用该纯函数；只有目标字段确实更新时才清除 `${target_field}_error`。

- [ ] **Step 4: 为主机（Telegraf）声明联动**

在 `server/apps/monitor/support-files/plugins/Telegraf/host/os/UI.json` 的 `node_ids` 列增加：

```json
"change_handler": {
  "type": "option_field",
  "source_field": "name",
  "target_field": "instance_name"
}
```

实例名称列保持普通可编辑 `input`。

- [ ] **Step 5: 运行聚焦验证并确认绿灯**

Run:

```bash
cd web
pnpm test:monitor-table-change-handler
pnpm exec eslint src/app/monitor/hooks/integration/tableChangeHandler.ts src/app/monitor/hooks/integration/useConfigRenderer.tsx scripts/monitor-table-change-handler-test.ts
pnpm type-check
```

Expected: 聚焦测试通过；改动文件 ESLint 通过；TypeScript 类型检查通过。若全量类型检查命中已有无关错误，记录具体错误但不扩改。

- [ ] **Step 6: 检查配置与提交**

Run:

```bash
jq empty server/apps/monitor/support-files/plugins/Telegraf/host/os/UI.json
git diff --check
```

Expected: JSON 合法，diff 无空白错误。

Commit:

```bash
git add web/package.json web/scripts/monitor-table-change-handler-test.ts web/src/app/monitor/hooks/integration/tableChangeHandler.ts web/src/app/monitor/hooks/integration/useConfigRenderer.tsx server/apps/monitor/support-files/plugins/Telegraf/host/os/UI.json
git commit -m "功能(监控): 节点名称默认填入主机实例"
```
