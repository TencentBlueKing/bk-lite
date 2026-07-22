# Historical Superpowers change: 2026-07-09-monitor-telegraf-node-instance-name-default

Status: done

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-09-monitor-telegraf-node-instance-name-default.md

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

- [x] **Step 1: 写失败测试**

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

- [x] **Step 2: 运行测试并确认红灯**

Run: `cd web && pnpm test:monitor-table-change-handler`

Expected: FAIL，提示 `tableChangeHandler` 模块不存在。

- [x] **Step 3: 实现最小纯函数并接入渲染器**

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

- [x] **Step 4: 为主机（Telegraf）声明联动**

在 `server/apps/monitor/support-files/plugins/Telegraf/host/os/UI.json` 的 `node_ids` 列增加：

```json
"change_handler": {
  "type": "option_field",
  "source_field": "name",
  "target_field": "instance_name"
}
```

实例名称列保持普通可编辑 `input`。

- [x] **Step 5: 运行聚焦验证并确认绿灯**

Run:

```bash
cd web
pnpm test:monitor-table-change-handler
pnpm exec eslint src/app/monitor/hooks/integration/tableChangeHandler.ts src/app/monitor/hooks/integration/useConfigRenderer.tsx scripts/monitor-table-change-handler-test.ts
pnpm type-check
```

Expected: 聚焦测试通过；改动文件 ESLint 通过；TypeScript 类型检查通过。若全量类型检查命中已有无关错误，记录具体错误但不扩改。

- [x] **Step 6: 检查配置与提交**

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

## specs: 2026-07-09-monitor-telegraf-node-instance-name-default-design.md

- 日期：2026-07-09
- 范围：监控系统 / 主机（Telegraf）采集接入
- 状态：已确认

## 背景

主机（Telegraf）采集配置以表格方式选择采集节点并填写实例名称。当前选择节点后，实例名称仍为空，需要用户重复输入节点名称。

## 产品决策

选择节点时，以该节点的真实名称作为实例名称默认值。自动填入仅减少重复输入，不建立持续绑定；用户随后可以修改实例名称。

该行为仅配置给主机（Telegraf）采集，不影响其他插件。

## 交互规则

1. 用户选择节点后，实例名称立即填入所选节点的 `name`。
2. 下拉框展示文本包含“节点名称（IP）”时，实例名称仍只取节点真实名称，不包含 IP 或展示格式。
3. 用户手动修改实例名称后，当前值正常保留。
4. 用户再次选择其他节点时，以新节点名称重新填入实例名称；用户仍可继续修改。
5. 清空节点时，不主动清空实例名称，避免误删用户已经编辑的内容。

## 技术设计

扩展通用表格列配置的 `change_handler`，增加“从当前下拉选项读取字段”的声明式取值能力：

- 节点列变更时，根据选中的节点 ID 从该列选项中找到完整节点数据。
- 从匹配节点的 `name` 读取源值，并写入 `instance_name`。
- 复用现有目标字段更新与错误清理逻辑。
- 主机（Telegraf）的 `node_ids` 列单独声明该处理器；其他插件未声明时维持现状。

不在页面组件中按插件名称写条件判断，也不改变实例名称输入框的可编辑状态。

## 异常与边界

- 找不到对应节点选项或节点没有有效名称时，不覆盖现有实例名称。
- 节点列表异步加载完成前不触发默认值计算。
- 节点名称重复不影响处理：选项按节点 ID 定位，名称只作为默认展示值。
- 提交和后端数据结构保持不变。

## 测试与验收

采用 TDD，至少覆盖：

1. 选择节点后，目标字段得到节点的真实名称。
2. 下拉展示为“名称（IP）”时，实例名称不包含 IP。
3. 用户修改实例名称后，不发生额外自动覆盖。
4. 重新选择节点后，实例名称更新为新节点名称。
5. 找不到节点或节点名称为空时，保留原实例名称。
6. 未配置新处理器的其他表格列维持原有行为。

验收标准：在监控系统新建主机（Telegraf）采集配置，选择节点后实例名称自动显示节点名称，输入框仍可编辑，保存参数格式不变。
