# 运营分析“多值”图表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增接收 `[{ label, value }]` 的 `multiValue` 图表，并在普通仪表盘、大屏和拓扑图表节点中以可滚动的紧凑列表展示。

**Architecture:** 将数据规范化与校验放在无 React 依赖的纯函数模块中，供请求校验和展示组件共享；新增独立 `ComMultiValue`，通过现有 widget registry 接入所有承载面。普通仪表盘和拓扑沿用通用图表链路，大屏补充闭合类型和组件目录定义。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design 5、项目内 `tsx` 聚焦测试脚本、ESLint。

## Global Constraints

- 图表标识固定为 `multiValue`，显示名称为“多值”/“Multi-value”。
- 输入必须是 JSON 数组，每项同时包含 `label` 和 `value`。
- 字符串、数字正常显示；`null`、`undefined`、空字符串显示 `--`；对象和数组无效。
- 每行 label 左对齐、value 右对齐；长文本省略并提供 Tooltip；超高时仅组件内部纵向滚动。
- 首版不增加字段映射、单位、精度、阈值、值映射、排序、搜索或分页。
- 三种承载面共享同一组件，不新增拓扑节点类型。
- 严格按 TDD 顺序：失败测试、最小实现、通过测试。
- 不执行 `git add`、`git commit` 或 `git push`；提交由用户手动完成。
- 不改动用户已有的 `web/package.json` 修改；聚焦测试直接使用 `pnpm.cmd exec tsx`。

---

## File Structure

- Create: `web/src/app/ops-analysis/utils/multiValueData.ts` — 多值条目规范化与校验。
- Create: `web/src/app/ops-analysis/components/widgets/comMultiValue.tsx` — 列表展示、Tooltip 和滚动。
- Create: `web/scripts/ops-analysis-multi-value-test.ts` — 数据契约、注册和三承载面聚焦测试。
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx` — 接入统一校验。
- Modify: `web/src/app/ops-analysis/components/widgetRegistry.ts` — 注册组件。
- Modify: `web/src/app/ops-analysis/constants/common.ts`, `types/dataSource.ts`, `components/widgetSelector.tsx` — 数据源与普通仪表盘接入。
- Modify: `web/src/app/ops-analysis/types/screen.ts`, `(pages)/view/screen/constants/widgets.ts` — 大屏接入。
- Modify: `web/src/app/ops-analysis/locales/zh.json`, `en.json` — 翻译。

### Task 1: 多值数据契约与统一校验

**Files:**
- Create: `web/src/app/ops-analysis/utils/multiValueData.ts`
- Create: `web/scripts/ops-analysis-multi-value-test.ts`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`

**Interfaces:**
- Produces: `MultiValueItem`、`MultiValueValidationResult`、`validateMultiValueData(data, errorMessage)`。
- Consumes: 现有 `{ isValid: boolean; errorMessage?: string }` 图表校验约定。

- [ ] **Step 1: 编写失败测试**

创建测试脚本并写入：

```ts
import assert from 'node:assert/strict';
import { validateMultiValueData } from '../src/app/ops-analysis/utils/multiValueData';

const mismatch = 'format mismatch';

assert.deepEqual(
  validateMultiValueData([
    { label: 'CPU', value: 80 },
    { label: 2, value: '65%' },
  ], mismatch),
  {
    isValid: true,
    items: [
      { label: 'CPU', value: '80' },
      { label: '2', value: '65%' },
    ],
  },
);

assert.deepEqual(
  validateMultiValueData([
    { label: null, value: '' },
    { label: 'disk', value: undefined },
  ], mismatch),
  {
    isValid: true,
    items: [
      { label: '--', value: '--' },
      { label: 'disk', value: '--' },
    ],
  },
);

for (const invalid of [
  {},
  [{ label: 'CPU' }],
  [{ value: 80 }],
  [{ label: 'CPU', value: { nested: true } }],
  [{ label: ['CPU'], value: 80 }],
]) {
  assert.deepEqual(validateMultiValueData(invalid, mismatch), {
    isValid: false,
    errorMessage: mismatch,
    items: [],
  });
}

assert.deepEqual(validateMultiValueData([], mismatch), {
  isValid: true,
  items: [],
});
```

- [ ] **Step 2: 运行 RED**

Run from `web/`:

```powershell
pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts
```

Expected: FAIL，提示找不到 `multiValueData` 模块或导出。

- [ ] **Step 3: 实现纯函数**

```ts
export interface MultiValueItem {
  label: string;
  value: string;
}

export interface MultiValueValidationResult {
  isValid: boolean;
  errorMessage?: string;
  items: MultiValueItem[];
}

const normalizeScalar = (value: unknown): string | null => {
  if (value == null || value === '') return '--';
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  return null;
};

export const validateMultiValueData = (
  data: unknown,
  errorMessage: string,
): MultiValueValidationResult => {
  if (!Array.isArray(data)) {
    return { isValid: false, errorMessage, items: [] };
  }

  const items: MultiValueItem[] = [];
  for (const entry of data) {
    if (
      entry == null ||
      typeof entry !== 'object' ||
      Array.isArray(entry) ||
      !Object.prototype.hasOwnProperty.call(entry, 'label') ||
      !Object.prototype.hasOwnProperty.call(entry, 'value')
    ) {
      return { isValid: false, errorMessage, items: [] };
    }
    const record = entry as Record<string, unknown>;
    const label = normalizeScalar(record.label);
    const value = normalizeScalar(record.value);
    if (label == null || value == null) {
      return { isValid: false, errorMessage, items: [] };
    }
    items.push({ label, value });
  }
  return { isValid: true, items };
};
```

- [ ] **Step 4: 接入请求校验**

在 `widgetDataRenderer.tsx` 导入函数，并在 `validateChartData` 的 switch 中加入：

```ts
case 'multiValue':
  return validateMultiValueData(data, errorMessage);
```

保留空数组提前返回合法空状态的现有行为。

- [ ] **Step 5: 验证 GREEN**

```powershell
pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts
pnpm.cmd exec eslint src/app/ops-analysis/utils/multiValueData.ts src/app/ops-analysis/components/widgetDataRenderer.tsx scripts/ops-analysis-multi-value-test.ts
```

Expected: 测试通过，ESLint 退出码 0。报告检查点，不进行 Git 写操作。

### Task 2: 紧凑列表组件与注册

**Files:**
- Create: `web/src/app/ops-analysis/components/widgets/comMultiValue.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetRegistry.ts`
- Modify: `web/scripts/ops-analysis-multi-value-test.ts`

**Interfaces:**
- Consumes: `validateMultiValueData`，以及 WidgetRenderer 的 `rawData`、`loading`、`screenRenderContext`、`onReady`。
- Produces: 默认导出的 `ComMultiValue` 和 `widgetRegistry.multiValue`。

- [ ] **Step 1: 添加失败断言**

```ts
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ComMultiValue from '../src/app/ops-analysis/components/widgets/comMultiValue';
import { getWidgetComponent } from '../src/app/ops-analysis/components/widgetRegistry';

const markup = renderToStaticMarkup(
  React.createElement(ComMultiValue, {
    rawData: [
      { label: 'CPU', value: 80 },
      { label: 'CPU', value: '65%' },
    ],
  }),
);

assert.match(markup, /data-testid="multi-value-scroll"/);
assert.match(markup, /overflow-y-auto/);
assert.match(markup, />CPU</);
assert.match(markup, />80</);
assert.equal(getWidgetComponent('multiValue'), ComMultiValue);
```

- [ ] **Step 2: 运行 RED**

Run: `pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts`

Expected: FAIL，找不到组件或注册结果为 null。

- [ ] **Step 3: 实现组件**

组件使用 Ant Design `Empty`、`Spin`、`Tooltip`，并按 `comSingle.tsx` 的现有方式调用 `getScreenWidgetScale`：

```tsx
interface ComMultiValueProps {
  rawData?: unknown;
  loading?: boolean;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready?: boolean) => void;
}

const ComMultiValue: React.FC<ComMultiValueProps> = ({
  rawData,
  loading = false,
  screenRenderContext,
  onReady,
}) => {
  const { t } = useTranslation();
  const result = validateMultiValueData(
    rawData ?? [],
    t('dashboard.dataFormatMismatch'),
  );
  const scale = getScreenWidgetScale(screenRenderContext);

  useEffect(() => {
    onReady?.(!loading);
  }, [loading, onReady]);

  if (loading) return <Spin />;
  if (!result.isValid || result.items.length === 0) return <Empty />;

  return (
    <div
      data-testid="multi-value-scroll"
      className="h-full min-h-0 overflow-x-hidden overflow-y-auto"
    >
      {result.items.map((item, index) => (
        <div
          key={`${item.label}-${index}`}
          className="flex min-w-0 items-center justify-between border-b border-[var(--color-border-2)] last:border-b-0"
          style={{ gap: 16 * scale, padding: `${10 * scale}px ${12 * scale}px` }}
        >
          <Tooltip title={item.label}>
            <span className="min-w-0 flex-1 truncate text-[var(--color-text-2)]">
              {item.label}
            </span>
          </Tooltip>
          <Tooltip title={item.value}>
            <span className="min-w-0 max-w-[55%] shrink-0 truncate text-right font-semibold text-[var(--color-text-1)]">
              {item.value}
            </span>
          </Tooltip>
        </div>
      ))}
    </div>
  );
};
```

如缩放函数实际签名不同，只按 `comSingle.tsx` 调整调用参数，不改变列表接口和行为。

- [ ] **Step 4: 注册组件**

```ts
import ComMultiValue from '@/app/ops-analysis/components/widgets/comMultiValue';

// widgetRegistry
multiValue: ComMultiValue,
```

- [ ] **Step 5: 验证 GREEN**

```powershell
pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts
pnpm.cmd exec eslint src/app/ops-analysis/components/widgets/comMultiValue.tsx src/app/ops-analysis/components/widgetRegistry.ts scripts/ops-analysis-multi-value-test.ts
```

Expected: 重复 label 均渲染、注册断言通过、ESLint 退出码 0。不进行 Git 写操作。

### Task 3: 数据源、普通仪表盘、大屏与拓扑接入

**Files:**
- Modify: `web/src/app/ops-analysis/constants/common.ts`
- Modify: `web/src/app/ops-analysis/types/dataSource.ts`
- Modify: `web/src/app/ops-analysis/components/widgetSelector.tsx`
- Modify: `web/src/app/ops-analysis/types/screen.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Modify: `web/scripts/ops-analysis-multi-value-test.ts`

**Interfaces:**
- Consumes: Task 2 的注册组件。
- Produces: `ChartType`、`ScreenWidgetChartType` 和各选择器/目录所需翻译键。

- [ ] **Step 1: 添加失败的接入断言**

```ts
import fs from 'node:fs';
import path from 'node:path';

const read = (relative: string) =>
  fs.readFileSync(path.resolve(process.cwd(), relative), 'utf8');

assert.match(read('src/app/ops-analysis/types/dataSource.ts'), /\| 'multiValue'/);
assert.match(read('src/app/ops-analysis/types/screen.ts'), /\| 'multiValue'/);
assert.match(read('src/app/ops-analysis/constants/common.ts'), /dataSource\.multiValue[\s\S]*multiValue/);
assert.match(read('src/app/ops-analysis/components/widgetSelector.tsx'), /multiValue:\s*t\('dataSource\.multiValue'\)/);

const screenWidgets = read('src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts');
assert.match(screenWidgets, /chartType:\s*'multiValue'/);
assert.match(screenWidgets, /defaultWidth:\s*360/);
assert.match(screenWidgets, /defaultHeight:\s*260/);

for (const locale of ['zh', 'en']) {
  const messages = JSON.parse(read(`src/app/ops-analysis/locales/${locale}.json`));
  assert.equal(typeof messages.dataSource.multiValue, 'string');
  assert.equal(typeof messages.opsAnalysis.screen.widgets.multiValue, 'string');
  assert.equal(typeof messages.opsAnalysis.screen.widgetDescriptions.multiValue, 'string');
}
```

- [ ] **Step 2: 运行 RED**

Run: `pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts`

Expected: FAIL，首个缺失的 `multiValue` 类型、目录项或翻译键被报告。

- [ ] **Step 3: 接入数据源和普通仪表盘**

```ts
// types/dataSource.ts ChartType
| 'multiValue'

// constants/common.ts getChartTypeList()
{ label: 'dataSource.multiValue', value: 'multiValue' },

// widgetSelector.tsx chartTypeLabels
multiValue: t('dataSource.multiValue'),
```

不在 `widgetConfig.tsx` 添加专属配置区；通用数据源、参数、刷新和保存链路保留 `chartType: 'multiValue'`。

- [ ] **Step 4: 接入大屏**

在 `ScreenWidgetChartType` 加入 `| 'multiValue'`，并向 `SCREEN_WIDGET_DEFINITIONS` 加入：

```ts
{
  chartType: 'multiValue',
  titleKey: 'opsAnalysis.screen.widgets.multiValue',
  descriptionKey: 'opsAnalysis.screen.widgetDescriptions.multiValue',
  defaultWidth: 360,
  defaultHeight: 260,
},
```

- [ ] **Step 5: 补充翻译**

`dataSource.multiValue` 和 `opsAnalysis.screen.widgets.multiValue` 分别使用“多值”/“Multi-value”。描述分别为：

```text
逐行展示名称和值，适合紧凑查看多项运营指标
Show label/value pairs row by row for compact operational summaries
```

- [ ] **Step 6: 锁定拓扑通用链路**

测试脚本增加：

```ts
const topologyChartNode = read(
  'src/app/ops-analysis/(pages)/view/topology/components/chartNode.tsx',
);
assert.match(topologyChartNode, /chartType=\{chartType\}/);
```

若断言通过，不修改拓扑文件：`chart` 节点现有的 `valueConfig.chartType -> WidgetRenderer -> widgetRegistry` 链路已经支持 `multiValue`，且不新增节点类型或序列化字段。

- [ ] **Step 7: 验证 GREEN**

```powershell
pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts
pnpm.cmd exec eslint src/app/ops-analysis/constants/common.ts src/app/ops-analysis/types/dataSource.ts src/app/ops-analysis/components/widgetSelector.tsx src/app/ops-analysis/types/screen.ts "src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts" scripts/ops-analysis-multi-value-test.ts
```

Expected: 三承载面和国际化断言通过，ESLint 退出码 0。不进行 Git 写操作。

### Task 4: 完整回归与验收

**Files:**
- Verify: Task 1–3 的全部文件
- Verify: `docs/superpowers/specs/2026-07-21-ops-analysis-multi-value-chart-design.md`

**Interfaces:**
- Consumes: 完整的多值数据、组件和三承载面接入。
- Produces: 验证证据，不新增业务接口。

- [ ] **Step 1: 运行聚焦和邻近回归**

```powershell
pnpm.cmd exec tsx scripts/ops-analysis-multi-value-test.ts
pnpm.cmd exec tsx scripts/ops-analysis-component-param-switch-test.ts
pnpm.cmd exec tsx scripts/ops-analysis-date-range-canvas-binding-test.ts
pnpm.cmd exec tsx scripts/ops-analysis-network-topology-test.ts
```

Expected: 四个脚本均退出码 0。

- [ ] **Step 2: 运行 touched-file ESLint**

```powershell
pnpm.cmd exec eslint src/app/ops-analysis/utils/multiValueData.ts src/app/ops-analysis/components/widgets/comMultiValue.tsx src/app/ops-analysis/components/widgetDataRenderer.tsx src/app/ops-analysis/components/widgetRegistry.ts src/app/ops-analysis/constants/common.ts src/app/ops-analysis/types/dataSource.ts src/app/ops-analysis/components/widgetSelector.tsx src/app/ops-analysis/types/screen.ts "src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts" scripts/ops-analysis-multi-value-test.ts
```

Expected: 退出码 0，无 warning/error。

- [ ] **Step 3: 运行类型检查**

```powershell
pnpm.cmd type-check
```

Expected: 退出码 0。若出现仓库既有无关错误或超时，只记录命令、首个无关错误以及 touched files 未出现在诊断中的证据，不修复范围外问题。

- [ ] **Step 4: 检查差异范围**

Run from repository root:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` 无输出；状态只包含用户原有修改、可视化草稿、设计/计划文档和本功能文件。

- [ ] **Step 5: 手工验收三种承载面**

使用：

```json
[
  { "label": "CPU", "value": 80 },
  { "label": "内存", "value": "65%" },
  { "label": "磁盘使用率很长的展示名称", "value": "42.123456789%" }
]
```

依次确认普通仪表盘、大屏和拓扑图表节点均满足：一行一个 label/value、左右对齐、长文本 Tooltip、内部滚动、空数组空状态、错误对象格式提示。

- [ ] **Step 6: 交付用户手动提交**

报告完成项、所有验证命令及任何仓库既有阻塞；明确没有暂存、提交或推送，将版本控制交给用户。

