# 告警列表页面问答 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让监控告警中心的活跃/历史列表（以及打开的那条详情和 Event）在发送时进入 Opspilot 当轮 `page_context`。

**Architecture:** 列表用与页面同目录的 `alert.pilot.ts` 只读 URL/DOM；详情因 Tab 互斥和虚拟列表无法靠 DOM 读全，用纯函数 `alertDetail.context.ts` 生成 section，由 `AlertDetail` 在打开时预取 Event 并通过 `useAiPageContext` 注册。registry 把 hook 与 pilot 合并。不改 GlobalWebchat、不改后端注入、不截 Recharts。

**Tech Stack:** Next.js App Router、Vitest + jsdom、现有 `ai-page-context` / codegen。

**规格:** `specs/changes/monitor-alert-page-context/spec.md`  
**验证:** `cd web && pnpm exec vitest run '<path>'`（路径含 `(pages)` 时必须加引号）  
**提交:** 仅在用户明确要求时执行各 Task 的 commit 步；默认做到测试通过即可。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `web/src/app/monitor/(pages)/event/alert/alert.pilot.ts` | 列表旁路：闸门、指纹、筛选/分页/当前页表行文字；`images: []` |
| `web/src/app/monitor/(pages)/event/alert/alertDetail.context.ts` | 详情快照纯函数：身份、字段、Event 最近 30 条 |
| `web/src/app/monitor/(pages)/event/alert/alertDetail.tsx` | 打开即预取 Event；抽屉可见时 `useAiPageContext` |
| `web/src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts` | 列表 jsdom 契约 |
| `web/src/app/monitor/(pages)/event/alert/__tests__/alertDetail.context.test.ts` | 详情纯函数契约 |
| `web/src/app/monitor/(pages)/event/alert/__tests__/alertDetail.eventTimeline.test.tsx` | 打开详情即请求 Event（改现有用例） |
| `web/src/components/ai-page-context/__tests__/generate-ai-pilots.test.ts` | 前缀 `/monitor/event/alert/` |
| `web/src/components/ai-page-context/pilots.generated.ts` | codegen 生成，提交进 git |

约定的 section id（后面任务必须用这些名字）：

- 列表：`alert-list-identity`(10)、`alert-list-range`(8)、`alert-list-chart`(6)、`alert-list-table`(4)
- 详情：`alert-detail-identity`(10)、`alert-detail-fields`(9)、`alert-detail-events`(8)

---

### Task 1: 列表闸门与缓存键

**Files:**
- Create: `web/src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts`
- Create: `web/src/app/monitor/(pages)/event/alert/alert.pilot.ts`
- Modify: `web/src/components/ai-page-context/__tests__/generate-ai-pilots.test.ts`

- [ ] **Step 1: 在 generate-ai-pilots 测试里锁路径前缀**

在 `pathnamePrefixFromPilotFile` 的 it 里加：

```ts
expect(pathnamePrefixFromPilotFile('monitor/(pages)/event/alert/alert.pilot.ts')).toBe(
  '/monitor/event/alert/',
);
```

- [ ] **Step 2: 跑 codegen 测试，确认前缀断言失败或已通过（文件尚未存在时只测字符串函数，应通过）**

Run:

```bash
cd web && pnpm exec vitest run src/components/ai-page-context/__tests__/generate-ai-pilots.test.ts
```

Expected: PASS（这步只测路径推导函数）。

- [ ] **Step 3: 写列表 pilot 失败测试**

`alert.pilot.test.ts`：

```ts
import { afterEach, describe, expect, it } from 'vitest';

import {
  buildAlertListCurrentTime,
  getMessage,
  getTextContext,
  readAlertListStamp,
} from '../alert.pilot';

const setAlertView = (search = '') => {
  window.history.replaceState({}, '', `/monitor/event/alert${search}`);
};

const alertListShell = (body: string, tab = 'activeAlarms') => `
  <div class="alert_alert_x">
    <div class="filters_filters_x">
      <span class="ant-tree-node-selected">主机</span>
    </div>
    <div class="alarmList_alarmList_x">
      <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="${tab}">活跃告警</div>
      <div class="ant-tabs-tab" data-node-key="historicalAlarms">历史告警</div>
      ${body}
    </div>
  </div>
`;

describe('alert.pilot gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('');
  });

  it('does not produce a page snapshot on extra tabs', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = `
      <div class="alarmList_alarmList_x">
        <div class="ant-tabs-tab ant-tabs-tab-active" data-node-key="related-topology">关联拓扑</div>
      </div>
    `;
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses tab and objId in title on host tabs', () => {
    setAlertView('?objId=12');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul><li><span>级别</span></li></ul>
        </div>
      </div>
      <div class="table_table_x"><table></table></div>
    `);
    expect(getMessage().title).toBe('monitor-alert:activeAlarms:12');
  });
});

describe('alert.pilot fingerprint', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('?objId=all');
  });

  it('changes currentTime when filters change, not when only refresh interval changes', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul>
            <li>
              <span>级别</span>
              <div class="ant-select"><span class="ant-select-selection-item">严重</span></div>
            </li>
          </ul>
          <div class="timeSelector_x">
            <div class="refreshBox_x"><div class="ant-select-selection-item">30秒</div></div>
          </div>
        </div>
      </div>
      <div class="table_table_x">
        <table>
          <thead><tr><th>级别</th><th>告警名称</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row"><td>严重</td><td>CPU 高</td></tr>
          </tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-total-text">共 1 项</li>
          <li class="ant-pagination-item ant-pagination-item-1 ant-pagination-item-active">1</li>
        </ul>
      </div>
    `);
    const first = buildAlertListCurrentTime(readAlertListStamp());
    document.querySelector('.refreshBox_x .ant-select-selection-item')!.textContent = '1分钟';
    const intervalOnly = buildAlertListCurrentTime(readAlertListStamp());
    expect(intervalOnly).toBe(first);
    document.querySelector('.condition_x .ant-select-selection-item')!.textContent = '警告';
    const filterChanged = buildAlertListCurrentTime(readAlertListStamp());
    expect(filterChanged).not.toBe(first);
  });
});
```

- [ ] **Step 4: 跑列表测试，确认失败（模块不存在）**

Run:

```bash
cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts'
```

Expected: FAIL，找不到 `../alert.pilot`。

- [ ] **Step 5: 实现闸门、title、currentTime**

`alert.pilot.ts` 最小实现（后续 Task 往同一文件加 section，不要另起文件）：

```ts
import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';

const TITLE_PREFIX = 'monitor-alert:';
const HOST_TABS = new Set(['activeAlarms', 'historicalAlarms']);
const COUNT_PLACEHOLDER = /已选\s*\d+\s*项/;
const EMPTY_HINT = /暂无数据|无数据|No [Dd]ata/;

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const listRoot = () => document.querySelector<HTMLElement>('[class*="alarmList"]');

const activeHostTab = (): string => {
  const active = listRoot()?.querySelector('.ant-tabs-tab-active');
  const key = active?.getAttribute('data-node-key') || '';
  return HOST_TABS.has(key) ? key : '';
};

export const isHostAlertListView = (): boolean => Boolean(activeHostTab());

const objIdFromSearch = (search = typeof window === 'undefined' ? '' : window.location.search) =>
  new URLSearchParams(search).get('objId') || 'all';

export interface AlertListStamp {
  tab: string;
  objId: string;
  objectLabel: string;
  filterText: string;
  rangeText: string;
  rowFingerprint: string;
  chartText: string;
  loading: boolean;
  emptyText: string;
}

const titledNames = (root: Element | null): string => {
  if (!root) return '';
  const titled = [root, ...Array.from(root.querySelectorAll('[title]'))].find(
    (node) => node instanceof HTMLElement && node.title && !COUNT_PLACEHOLDER.test(node.title),
  );
  return titled instanceof HTMLElement ? cleanLabel(titled.title) : '';
};

const readSelectValue = (group: Element): string => {
  const items = Array.from(group.querySelectorAll('.ant-select-selection-item'))
    .filter((node) => !node.closest('[class*="refreshBox"]'))
    .map((node) => {
      const visible = cleanLabel(node.textContent || '');
      if (COUNT_PLACEHOLDER.test(visible)) {
        const names = titledNames(node);
        return names ? `${visible}（${names}）` : visible;
      }
      return visible;
    })
    .filter(Boolean);
  return [...new Set(items)].join('、');
};

const readFilterFields = (): string[] => {
  const condition = listRoot()?.querySelector('[class*="searchCondition"] [class*="condition"]');
  if (!condition) return [];
  const lines: string[] = [];
  Array.from(condition.querySelectorAll('ul > li')).forEach((item) => {
    const label = cleanLabel(item.querySelector('span')?.textContent || '').replace(/[:：]\s*$/, '');
    const value = readSelectValue(item);
    if (label) lines.push(value ? `${label}: ${value}` : `${label}:`);
  });
  const rangeRoot = condition.querySelector('[class*="customSlect"]');
  if (rangeRoot) {
    const range = readSelectValue(rangeRoot)
      || Array.from(rangeRoot.querySelectorAll<HTMLInputElement>('.ant-picker-input input'))
        .map((node) => cleanLabel(node.value || ''))
        .filter(Boolean)
        .join(' ~ ');
    lines.push(range ? `时间筛选: ${range}` : '时间筛选:');
  } else if (activeHostTab() === 'activeAlarms') {
    lines.push('活跃告警不按时间窗过滤');
  }
  const search = listRoot()?.querySelector<HTMLInputElement>('[class*="table"] input.ant-input');
  if (search?.value) lines.push(`搜索: ${cleanLabel(search.value)}`);
  return lines;
};

const readTableRows = (): string[] => {
  const table = listRoot()?.querySelector('[class*="table"]');
  if (!table) return [];
  const headerCells = Array.from(table.querySelectorAll('thead th')).map((cell, index, all) => {
    if (index === all.length - 1 && /详情|关闭|Detail|Close|操作/.test(cell.textContent || '')) return '';
    return cleanLabel(cell.textContent || '');
  });
  const header = headerCells.filter(Boolean).join(' | ');
  const bodyRows = Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row, .ant-table-tbody tr'))
    .filter((row) => !row.classList.contains('ant-table-measure-row'))
    .map((row) => {
      const cells = Array.from(row.querySelectorAll('td'));
      const usable = cells.filter((cell) => !cell.querySelector('button, .ant-btn'));
      return usable.map((cell) => cleanLabel(cell.textContent || '')).filter(Boolean).join(' | ');
    })
    .filter(Boolean);
  return [header, ...bodyRows].filter(Boolean);
};

const readRangeText = (): string => {
  const table = listRoot()?.querySelector('[class*="table"]');
  const total = cleanLabel(table?.querySelector('.ant-pagination-total-text')?.textContent || '');
  const page = cleanLabel(table?.querySelector('.ant-pagination-item-active')?.textContent || '');
  return [total, page ? `当前第 ${page} 页` : ''].filter(Boolean).join('；');
};

export const readAlertListStamp = (): AlertListStamp => {
  const tab = activeHostTab();
  const rows = readTableRows();
  const table = listRoot()?.querySelector('[class*="table"]');
  return {
    tab,
    objId: objIdFromSearch(),
    objectLabel: cleanLabel(document.querySelector('[class*="filters"] .ant-tree-node-selected')?.textContent || ''),
    filterText: readFilterFields().join('；'),
    rangeText: readRangeText(),
    rowFingerprint: rows.slice(0, 4).join('|'),
    chartText: '',
    loading: Boolean(table?.querySelector('.ant-spin-spinning')),
    emptyText: cleanLabel(table?.querySelector('.ant-empty-description')?.textContent || '')
      || (rows.length <= 1 ? (Array.from(table?.querySelectorAll('span') || [])
        .map((node) => cleanLabel(node.textContent || ''))
        .find((text) => EMPTY_HINT.test(text)) || '') : ''),
  };
};

export const buildAlertListCurrentTime = (stamp: AlertListStamp): string =>
  [stamp.tab, stamp.objId, stamp.filterText, stamp.rangeText, stamp.rowFingerprint, stamp.loading ? 'loading' : '']
    .filter(Boolean)
    .join('::');

export function getMessage(): PageContextMessage {
  if (!isHostAlertListView()) return { title: '' };
  const stamp = readAlertListStamp();
  const title = `${TITLE_PREFIX}${stamp.tab}:${stamp.objId}`;
  const currentTime = buildAlertListCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  if (!isHostAlertListView()) return { sections: [], images: [] };
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'monitor',
    title: document.title || '告警列表',
    sections: [],
    images: [],
  };
}

export async function getContext(_toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
```

本 Task 的 `getTextContext` 可以先空 sections；闸门和指纹测试不依赖表文案。`readFilterFields` / `readTableRows` 已写入，供指纹使用。

- [ ] **Step 6: 再跑列表测试**

Run:

```bash
cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts'
```

Expected: PASS。

---

### Task 2: 列表文字快照（筛选、分页、当前页行）

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts`
- Modify: `web/src/app/monitor/(pages)/event/alert/alert.pilot.ts`

- [ ] **Step 1: 追加失败测试**

同一测试文件增加：

```ts
describe('alert.pilot text context', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setAlertView('?objId=all');
  });

  it('includes identity, filters, page range, rendered rows, and skips action cells', () => {
    setAlertView('?objId=all');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x">
        <div class="condition_x">
          <ul>
            <li>
              <span>级别</span>
              <div class="ant-select">
                <span class="ant-select-selection-item"><span title="严重、警告">已选 2 项</span></span>
              </div>
            </li>
            <li>
              <span>状态</span>
              <div class="ant-select"><span class="ant-select-selection-item">活跃</span></div>
            </li>
          </ul>
        </div>
      </div>
      <div class="table_table_x">
        <input class="ant-input" value="CPU" />
        <table>
          <thead><tr><th>级别</th><th>告警名称</th><th>资产</th><th>操作</th></tr></thead>
          <tbody class="ant-table-tbody">
            <tr class="ant-table-row">
              <td>严重</td><td>CPU 高</td><td>host-a</td>
              <td><button class="ant-btn">详情</button><button class="ant-btn">关闭</button></td>
            </tr>
            <tr class="ant-table-row">
              <td>警告</td><td>磁盘高</td><td>host-b</td>
              <td><button class="ant-btn">详情</button></td>
            </tr>
          </tbody>
        </table>
        <ul class="ant-pagination">
          <li class="ant-pagination-total-text">共 40 项</li>
          <li class="ant-pagination-item ant-pagination-item-2 ant-pagination-item-active">2</li>
        </ul>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('正在查看告警列表');
    expect(text).toContain('活跃告警');
    expect(text).toContain('主机');
    expect(text).toContain('严重');
    expect(text).toContain('警告');
    expect(text).toContain('活跃告警不按时间窗过滤');
    expect(text).toContain('CPU');
    expect(text).toContain('共 40 项');
    expect(text).toContain('当前第 2 页');
    expect(text).toContain('CPU 高');
    expect(text).toContain('host-a');
    expect(text).toContain('磁盘高');
    expect(text).not.toContain('详情');
    expect(text).not.toContain('关闭');
  });

  it('copies all currently rendered rows instead of capping at 10', () => {
    setAlertView('?objId=all');
    const rows = Array.from({ length: 20 }, (_, index) =>
      `<tr class="ant-table-row"><td>row-${index + 1}</td><td>host-${index + 1}</td></tr>`,
    ).join('');
    document.body.innerHTML = alertListShell(`
      <div class="searchCondition_x"><div class="condition_x"><ul></ul></div></div>
      <div class="table_table_x">
        <table>
          <thead><tr><th>告警名称</th><th>资产</th></tr></thead>
          <tbody class="ant-table-tbody">${rows}</tbody>
        </table>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('row-1');
    expect(text).toContain('row-20');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```bash
cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts'
```

Expected: FAIL，`getTextContext().sections` 为空。

- [ ] **Step 3: 实现 sections**

把 Task 1 里空的 `getTextContext` 换成：

```ts
const listTextSections = (stamp: AlertListStamp): AiContextSection[] => {
  const identity = [
    '正在查看告警列表',
    stamp.tab === 'historicalAlarms' ? '视图: 历史告警' : stamp.tab ? '视图: 活跃告警' : '',
    stamp.objectLabel ? `对象: ${stamp.objectLabel}` : '',
    stamp.objId ? `objId: ${stamp.objId}` : '',
    stamp.filterText ? `当前筛选: ${stamp.filterText}` : '',
    stamp.loading ? '表格加载中' : '',
    stamp.emptyText ? `空态: ${stamp.emptyText}` : '',
  ].filter(Boolean);
  const rows = readTableRows();
  return [
    {
      id: 'alert-list-identity',
      label: '当前告警列表',
      content: identity.join('\n'),
      priority: 10,
    },
    ...(stamp.rangeText
      ? [{
        id: 'alert-list-range',
        label: '结果范围',
        content: stamp.rangeText,
        priority: 8,
      }]
      : []),
    ...(stamp.chartText
      ? [{
        id: 'alert-list-chart',
        label: '分布图',
        content: stamp.chartText,
        priority: 6,
      }]
      : []),
    ...(rows.length
      ? [{
        id: 'alert-list-table',
        label: '当前页告警',
        content: rows.join('\n'),
        priority: 4,
      }]
      : []),
  ];
};

export function getTextContext(): Partial<AiPageContext> {
  if (!isHostAlertListView()) return { sections: [], images: [] };
  const stamp = readAlertListStamp();
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'monitor',
    title: document.title || '告警列表',
    sections: listTextSections(stamp),
    images: [],
  };
}

export async function getContext(_toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  const base = getTextContext();
  const stamp = readAlertListStamp();
  console.info('[ai-page-context] page data updated at', buildAlertListCurrentTime(stamp), {
    tab: stamp.tab,
    objId: stamp.objId,
    timeRange: stamp.filterText || '(none)',
    range: stamp.rangeText,
  });
  return base;
}
```

历史告警的「视图」文案：当 `data-node-key` 为 `historicalAlarms` 时写「视图: 历史告警」。上面 `alertListShell` 默认 active。身份里用 tab key 映射即可，不要写死中文 Tab 标签对比（英文环境会失败）。筛选标签仍读 DOM（「级别」「Level」随页面语言）。

若「已选 2 项」展开测试失败，检查 `title` 是否在 `span` 上，`titledNames` 必须读到「严重、警告」。

- [ ] **Step 4: 再跑列表测试**

Expected: PASS。

---

### Task 3: 加载 / 空态 / 历史时间窗 / 预算

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts`

- [ ] **Step 1: 追加测试**

```ts
import { mergePageContexts } from '@/components/ai-page-context/registry';
import { PAGE_CONTEXT_TEXT_BUDGET } from '@/components/ai-page-context/types';

it('keeps identity when table rows exceed the text budget', () => {
  const hugeRows = Array.from({ length: 20 }, (_, index) => `row-${index}:${'x'.repeat(500)}`).join('\n');
  const merged = mergePageContexts([{
    sections: [
      { id: 'alert-list-identity', label: '当前告警列表', content: '正在查看告警列表\n当前筛选: 级别: 严重', priority: 10 },
      { id: 'alert-detail-identity', label: '当前告警详情', content: '告警: CPU 高', priority: 10 },
      { id: 'alert-detail-events', label: '事件', content: '共 3 条，已附最近 3 条', priority: 8 },
      { id: 'alert-list-table', label: '当前页告警', content: hugeRows, priority: 4 },
    ],
  }]);
  const ids = (merged.sections || []).map((section) => section.id);
  expect(ids).toContain('alert-list-identity');
  expect(ids).toContain('alert-detail-identity');
  expect((merged.sections || []).reduce((sum, section) => sum + section.content.length, 0))
    .toBeLessThanOrEqual(PAGE_CONTEXT_TEXT_BUDGET);
});

it('does not treat a loading overlay as zero alerts', () => {
  setAlertView('?objId=all');
  document.body.innerHTML = alertListShell(`
    <div class="searchCondition_x"><div class="condition_x"><ul></ul></div></div>
    <div class="table_table_x">
      <div class="ant-spin ant-spin-spinning"></div>
      <table><thead><tr><th>告警名称</th></tr></thead><tbody class="ant-table-tbody"></tbody></table>
    </div>
  `);
  const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
  expect(text).toContain('表格加载中');
});

it('includes historical time range copy', () => {
  setAlertView('?objId=all');
  document.body.innerHTML = alertListShell(`
    <div class="searchCondition_x">
      <div class="condition_x">
        <ul></ul>
        <div class="timeSelector_x">
          <div class="customSlect_x"><div class="ant-select-selection-item">最近7天</div></div>
          <div class="refreshBox_x"><div class="ant-select-selection-item">30秒</div></div>
        </div>
      </div>
    </div>
    <div class="table_table_x"><table></table></div>
  `, 'historicalAlarms');
  const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
  expect(getMessage().title).toBe('monitor-alert:historicalAlarms:all');
  expect(text).toContain('历史告警');
  expect(text).toContain('最近7天');
  expect(text).not.toContain('活跃告警不按时间窗过滤');
});
```

`alertListShell` 第二个参数已是 tab；历史用例必须把 `data-node-key` 设为 `historicalAlarms`。若 helper 只改 key、文案仍写「活跃告警」，身份 section 应看 **tab key** 映射，不要用 Tab 按钮中文。

- [ ] **Step 2: 跑测试；若历史时间窗读不到，在 `readFilterFields` 用 `[class*="customSlect"]` 而不是 refreshBox**

Run: 同上 vitest 命令。Expected: PASS。失败则只改 `readFilterFields` / 视图文案映射。

分布图：Collapse 折叠时 DOM 无 `.recharts-wrapper`。可选加一个测试：展开的 SVG 文本进入 `alert-list-chart`。若首轮读 Recharts 轴文案不稳定，允许 `chartText` 为空，但折叠不得误报数字。不要为了图表去改 `StackedBarChart`。

---

### Task 4: 生成 pilots.generated.ts

**Files:**
- Create/already: `alert.pilot.ts`
- Modify: `web/src/components/ai-page-context/pilots.generated.ts`

- [ ] **Step 1: 跑 codegen**

```bash
cd web && node scripts/generate-ai-pilots.mjs
```

Expected: 输出含 `ai-pilots`，`pilots.generated.ts` 增加：

```ts
{
  test: (pathname) => pathname.includes('/monitor/event/alert/'),
  load: () => import('@/app/monitor/(pages)/event/alert/alert.pilot'),
},
```

- [ ] **Step 2: 再跑 generate-ai-pilots 测试**

```bash
cd web && pnpm exec vitest run src/components/ai-page-context/__tests__/generate-ai-pilots.test.ts
```

Expected: PASS。不要手改 `pilots.ts`。

---

### Task 5: 详情快照纯函数

**Files:**
- Create: `web/src/app/monitor/(pages)/event/alert/__tests__/alertDetail.context.test.ts`
- Create: `web/src/app/monitor/(pages)/event/alert/alertDetail.context.ts`

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it } from 'vitest';

import { ALERT_DETAIL_EVENT_LIMIT, buildAlertDetailPageContext } from '../alertDetail.context';

const labels = {
  level: (value?: string) => ({ critical: '严重', warning: '警告' }[value || ''] || value || '--'),
  state: (value?: string) => ({ new: '活跃', closed: '关闭' }[value || ''] || value || '--'),
  alertType: (value?: string) => ({ alert: '阈值' }[value || ''] || value || '--'),
  action: (value?: string) => ({ triggered: '触发', recovered: '恢复' }[value || ''] || value || ''),
  formatTime: (value?: string) => value || '--',
  formatValue: (_metric: unknown, value: unknown) => String(value ?? ''),
};

describe('alertDetail.context', () => {
  it('returns no sections when the drawer is closed', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: false,
      formData: { id: 1, content: 'CPU 高' },
      eventData: [{ id: 'ev-1' }],
      labels,
    });
    expect(snapshot.sections || []).toEqual([]);
  });

  it('includes identity, fields, and events while still on the information tab', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      formData: {
        id: 9,
        content: 'CPU 超阈值',
        level: 'critical',
        status: 'new',
        alert_type: 'alert',
        updated_at: '2026-01-01 12:00:00',
        monitor_instance_name: 'host-a',
        policy: { name: 'CPU 策略' },
        metric: { display_name: 'CPU 使用率', dimensions: [{ name: 'host', description: '主机' }] },
        dimensions: { host: 'host-a' },
      },
      eventData: [
        { id: 'ev-1', event_time: '2026-01-01 12:00:00', action: 'triggered', level: 'critical', content: 'CPU 超阈值', value: 95 },
      ],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => `${section.id}\n${section.content}`).join('\n');
    expect(text).toContain('alert-detail-identity');
    expect(text).toContain('CPU 超阈值');
    expect(text).toContain('host-a');
    expect(text).toContain('CPU 策略');
    expect(text).toContain('触发');
    expect(text).toContain('95');
    expect(snapshot.sections?.find((section) => section.id === 'alert-detail-events')?.priority).toBe(8);
  });

  it('keeps the newest 30 events and writes the total', () => {
    const eventData = Array.from({ length: 35 }, (_, index) => ({
      id: `ev-${index}`,
      event_time: `2026-01-01T12:${String(index).padStart(2, '0')}:00Z`,
      action: 'triggered',
      level: 'critical',
      content: `event-${index}`,
      value: index,
    }));
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      formData: { id: 1, content: 'CPU 高' },
      eventData,
      labels,
    });
    const eventSection = snapshot.sections?.find((section) => section.id === 'alert-detail-events')?.content || '';
    expect(eventSection).toContain('共 35 条');
    expect(eventSection).toContain(`已附最近 ${ALERT_DETAIL_EVENT_LIMIT} 条`);
    expect(eventSection).toContain('event-34');
    expect(eventSection).toContain('event-5');
    expect(eventSection).not.toContain('event-4');
  });

  it('says events are loading instead of treating empty as zero', () => {
    const snapshot = buildAlertDetailPageContext({
      visible: true,
      pageLoading: false,
      eventLoading: true,
      formData: { id: 1, content: 'CPU 高' },
      eventData: [],
      labels,
    });
    const text = (snapshot.sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('事件加载中');
    expect(text).not.toContain('共 0 条');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alertDetail.context.test.ts'
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 `alertDetail.context.ts`**

```ts
import type { AiContextSection, AiPageContext } from '@/components/ai-page-context/types';
import { buildAlertDimensionDisplayItems } from './alertDimensionUtils';

export const ALERT_DETAIL_EVENT_LIMIT = 30;

export interface AlertDetailContextLabels {
  level: (value?: string) => string;
  state: (value?: string) => string;
  alertType: (value?: string) => string;
  action: (value?: string) => string;
  formatTime: (value?: string) => string;
  formatValue: (metric: unknown, value: unknown) => string;
}

export interface AlertDetailContextInput {
  visible: boolean;
  pageLoading?: boolean;
  eventLoading?: boolean;
  formData?: Record<string, any>;
  eventData?: Array<Record<string, any>>;
  trapData?: Record<string, any>;
  labels: AlertDetailContextLabels;
}

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const eventTimeValue = (item: Record<string, any>): number => {
  const raw = item.event_time;
  const ts = raw ? Date.parse(String(raw)) : Number.NaN;
  return Number.isFinite(ts) ? ts : 0;
};

export function buildAlertDetailPageContext(input: AlertDetailContextInput): Partial<AiPageContext> {
  if (!input.visible) return { sections: [], images: [] };
  const form = input.formData || {};
  const labels = input.labels;
  const identity = [
    '正在查看告警详情',
    form.id != null ? `告警 id: ${form.id}` : '',
    form.content ? `告警: ${form.content}` : '',
    `级别: ${labels.level(form.level)}`,
    `状态: ${labels.state(form.status)}`,
    `类型: ${labels.alertType(form.alert_type)}`,
    form.updated_at ? `时间: ${labels.formatTime(form.updated_at)}` : '',
    form.monitor_instance_name ? `资产: ${form.monitor_instance_name}` : '',
    input.pageLoading ? '详情加载中' : '',
  ].filter(Boolean);

  const dimensions = buildAlertDimensionDisplayItems(form.metric?.dimensions, form.dimensions)
    .map((item) => `${item.label}: ${item.value}`);
  const trapEntries = Object.entries(input.trapData || {}).map(([key, value]) => {
    const text = Array.isArray(value) ? String(value[0]?.[1] ?? '--') : String(value ?? '--');
    return `${key}: ${text}`;
  });
  const fieldLines = [
    ...dimensions,
    form.policy?.name ? `策略: ${form.policy.name}` : '',
    form.metric?.display_name ? `指标: ${form.metric.display_name}` : '',
    ...trapEntries,
  ].filter(Boolean);

  const allEvents = [...(input.eventData || [])].sort((left, right) => eventTimeValue(right) - eventTimeValue(left));
  const attached = allEvents.slice(0, ALERT_DETAIL_EVENT_LIMIT);
  const eventLines = input.eventLoading
    ? ['事件加载中']
    : allEvents.length
      ? [
        `共 ${allEvents.length} 条，已附最近 ${attached.length} 条`,
        ...attached.map((item) => cleanLabel([
          labels.formatTime(item.event_time),
          labels.action(item.action),
          labels.level(item.level),
          item.content || form.metric?.display_name || '',
          labels.formatValue(form.metric, item.value),
        ].filter(Boolean).join(' '))),
      ]
      : ['暂无事件'];

  const sections: AiContextSection[] = [
    { id: 'alert-detail-identity', label: '当前告警详情', content: identity.join('\n'), priority: 10 },
    ...(fieldLines.length
      ? [{ id: 'alert-detail-fields', label: '详情字段', content: fieldLines.join('\n'), priority: 9 }]
      : []),
    { id: 'alert-detail-events', label: '事件', content: eventLines.join('\n'), priority: 8 },
  ];
  return { app: 'monitor', sections, images: [] };
}
```

注意：`event-4` 被排除是因为按时间降序后最近 30 条是 `event-5`…`event-34`（index 5–34）。测试里时间是 `12:${index}`，index=4 是更早的，必须不出现。若 `Date.parse` 对 `2026-01-01 12:04:00` 无效，改用字符串比较或在测试里用 ISO 时间。

- [ ] **Step 4: 跑详情纯函数测试**

Expected: PASS。

---

### Task 6: 接到 AlertDetail（预取 Event + hook）

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/alert/alertDetail.tsx`
- Modify: `web/src/app/monitor/(pages)/event/alert/__tests__/alertDetail.eventTimeline.test.tsx`

- [ ] **Step 1: 改现有时间线测试——打开详情就请求 Event**

在 `展示动作文案…` 里，`showModal` 之后、点击「事件」之前增加：

```ts
await waitFor(() => {
  expect(getMonitorEventDetail).toHaveBeenCalledWith(
    1,
    expect.objectContaining({ page: 1, page_size: -1 }),
  );
});
```

点击「事件」仍可保留（刷新路径）。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alertDetail.eventTimeline.test.tsx'
```

Expected: FAIL，`getMonitorEventDetail` 在点击前未被调用。

- [ ] **Step 3: 最小接线**

1. import：

```ts
import { useAiPageContext } from '@/components/ai-page-context';
import { buildAlertDetailPageContext } from './alertDetail.context';
```

2. `showModal`：

```ts
showModal: ({ title, form }) => {
  setGroupVisible(true);
  setTitle(title);
  getMetrics(form);
  getEventData(form?.id);
}
```

3. 在 hooks 之后、return 之前注册（`groupVisible` 为 false 时 `visible: false`）：

```ts
useAiPageContext(
  () => buildAlertDetailPageContext({
    visible: groupVisible,
    pageLoading,
    eventLoading,
    formData,
    eventData,
    trapData,
    labels: {
      level: (value) => LEVEL_LIST.find((item) => item.value === value)?.label || value || '--',
      state: (value) => STATE_MAP[value || ''] || value || '--',
      alertType: (value) => ALERT_TYPE_MAP[value || ''] || value || '--',
      action: (value) => (value ? EVENT_ACTION_MAP[value as keyof typeof EVENT_ACTION_MAP] : '') || '',
      formatTime: (value) => (value ? convertToLocalizedTime(value) : '--'),
      formatValue: (metric, value) => String(getEnumValueUnit(metric, value) ?? ''),
    },
  }),
  [groupVisible, pageLoading, eventLoading, formData, eventData, trapData, LEVEL_LIST, STATE_MAP, ALERT_TYPE_MAP, EVENT_ACTION_MAP],
);
```

不要改抽屉 JSX、不要改信息/事件 Tab 展示。`changeTab` 里原有的 `getEventData` 保留。

`useAiPageContext` 的 deps 若 eslint 抱怨 maps，把 label 函数放进 `useMemo` 再传入，不要为了消警告改页面布局。

- [ ] **Step 4: 再跑详情相关测试**

```bash
cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alertDetail.eventTimeline.test.tsx' 'src/app/monitor/(pages)/event/alert/__tests__/alertDetail.context.test.ts' 'src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts'
```

Expected: 全部 PASS。

- [ ] **Step 5: 更新 spec 状态**

把 `specs/changes/monitor-alert-page-context/spec.md` 的 `Status: draft` 改为 `in-progress`；实现并验证后再改为 `done`，并在文末加一行验证命令。

---

## 手测（实现后，不替代单测）

1. `/monitor/event/alert` 活跃告警发送，请求带 `page_context`，含当前筛选和当前页行。
2. 改级别或翻页后再问，Console `[ai-page-context] page data updated at` 指纹变化。
3. 打开一条详情（停在信息 Tab）再问，文本含该条 id/名称和 Event。
4. 关掉详情再问，不再含该条详情。
5. `/monitor/event/strategy` 仍无 `page_context`。

---

## Spec coverage

| 规格条目 | Task |
|---|---|
| 只接活跃/历史 Tab，额外 Tab 裸聊 | 1 |
| title = tab + objId，刷新间隔不当时间窗 | 1 |
| 当前页全部已渲染行、去掉操作列、写共 N 条/页码 | 2 |
| 已选 N 项展开、活跃无时间窗、历史有时间窗 | 2、3 |
| 超 8K 保身份/详情 | 3 |
| codegen `/monitor/event/alert/` | 4 |
| 详情 hook + 打开即预取 Event + 最近 30 条 | 5、6 |
| 不改 GlobalWebchat / 后端 / Recharts 截图 | 全任务都不碰 |
| 列表不另打全量接口 | 1–3 只读 DOM |
