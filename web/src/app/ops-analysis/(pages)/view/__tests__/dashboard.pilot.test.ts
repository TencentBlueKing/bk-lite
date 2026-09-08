import { afterEach, describe, expect, it } from 'vitest';

import { mergePageContexts } from '@/components/ai-page-context/registry';
import {
  PAGE_CONTEXT_TEXT_BUDGET,
  type PageContextToolkit,
} from '@/components/ai-page-context/types';

import {
  buildOpsAnalysisCurrentTime,
  getContext,
  getMessage,
  getTextContext,
  isDecorativeOpsAnalysisChart,
  listScreenshotableChartDoms,
  readOpsAnalysisDashboardStamp,
} from '../dashboard.pilot';

const setView = (search: string) => {
  window.history.replaceState({}, '', `/ops-analysis/view${search}`);
};

const stubRect = (element: Element, rect: Partial<DOMRect>) => {
  (element as HTMLElement).getBoundingClientRect = () =>
    ({
      x: rect.left ?? 0,
      y: rect.top ?? 0,
      width: rect.width ?? 120,
      height: rect.height ?? 200,
      top: rect.top ?? 0,
      left: rect.left ?? 0,
      bottom: (rect.top ?? 0) + (rect.height ?? 200),
      right: (rect.left ?? 0) + (rect.width ?? 120),
      toJSON() {
        return this;
      },
    }) as DOMRect;
};

const dashboardShell = (body: string) => `
  <h2>生产总览</h2>
  <div data-export-hidden="true">
    <div class="ant-select-selection-item">30秒</div>
  </div>
  ${body}
`;

describe('ops-analysis dashboard.pilot type gate', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setView('');
  });

  it('does not produce a page snapshot when type is not dashboard', () => {
    setView('?type=topology&id=topo-1');
    document.body.innerHTML = dashboardShell('<div data-node-kind="widget"><div class="widget"><div class="widget-header"><h4>不该出现</h4></div></div></div>');
    expect(getMessage().title).toBe('');
    expect(getTextContext().sections || []).toEqual([]);
  });

  it('uses the canvas id in title when type=dashboard', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell('');
    expect(getMessage().title).toBe('ops-analysis-dashboard:dash-1');
  });
});

describe('ops-analysis dashboard.pilot filter fingerprint', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setView('?type=dashboard&id=dash-1');
  });

  it('changes currentTime when unified filter copy changes, not when only refresh interval changes', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium tracking-[0.02em]">时间:</span>
        <div class="ant-select-selection-item">最近15分钟</div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>CPU</h4></div>
          <div class="widget-body"><span class="font-semibold">22.4%</span></div>
        </div>
      </div>
    `);
    const first = buildOpsAnalysisCurrentTime(readOpsAnalysisDashboardStamp());
    document.querySelector('[data-export-hidden] .ant-select-selection-item')!.textContent = '60秒';
    const intervalOnly = buildOpsAnalysisCurrentTime(readOpsAnalysisDashboardStamp());
    expect(intervalOnly).toBe(first);
    document.querySelector('.flex.items-center .ant-select-selection-item')!.textContent = '最近6小时';
    const filterChanged = buildOpsAnalysisCurrentTime(readOpsAnalysisDashboardStamp());
    expect(filterChanged).not.toBe(first);
  });

  it('reads organization tree text and checked radio labels, not empty placeholders', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">统计维度:</span>
        <div class="ant-radio-group">
          <label class="ant-radio-button-wrapper-checked">模型</label>
          <label class="ant-radio-button-wrapper">实例</label>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">模型ID:</span>
        <input placeholder="模型ID" value="" />
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">组织ID:</span>
        <div><div class="flex-1 overflow-hidden">Default / TestSubOrg</div></div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">时间范围:</span>
        <div class="ant-select-selection-item">最近30天</div>
      </div>
    `);
    expect(readOpsAnalysisDashboardStamp().filterText).toBe(
      '统计维度: 模型；模型ID:；组织ID: Default / TestSubOrg；时间范围: 最近30天',
    );
  });

  it('expands table-select count placeholders using the rest-tag title', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">主机:</span>
        <div class="ant-select">
          <span class="ant-select-selection-item"><span title="MOBILE-DEMO-HOST-01、UX-DEMO web-01">已选 2 项</span></span>
        </div>
      </div>
    `);
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('主机:');
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('MOBILE-DEMO-HOST-01');
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('UX-DEMO web-01');
  });

  it('reads checked host names from an open table-select modal', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">主机:</span>
        <div class="ant-select">
          <span class="ant-select-selection-item">已选 2 项</span>
        </div>
      </div>
      <div class="ant-modal-wrap">
        <div class="ant-modal" role="dialog">
          <div class="ant-modal-title">主机</div>
          <table>
            <tbody>
              <tr class="ant-table-row-selected">
                <td class="ant-table-selection-column"><label class="ant-checkbox-wrapper"><span class="ant-checkbox"><input type="checkbox" checked /></span></label></td>
                <td>MOBILE-DEMO-HOST-01 (10.250.10.21)</td>
              </tr>
              <tr>
                <td class="ant-table-selection-column"><label class="ant-checkbox-wrapper"><span class="ant-checkbox"><input type="checkbox" /></span></label></td>
                <td>skip-me</td>
              </tr>
              <tr class="ant-table-row-selected">
                <td class="ant-table-selection-column"><label class="ant-checkbox-wrapper"><span class="ant-checkbox"><input type="checkbox" checked /></span></label></td>
                <td>UX-DEMO web-01 (10.250.10.11)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `);
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('MOBILE-DEMO-HOST-01');
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('UX-DEMO web-01');
    expect(readOpsAnalysisDashboardStamp().filterText).not.toContain('skip-me');
  });

  it('joins multiple select tags and custom date inputs', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">对象:</span>
        <div class="ant-select">
          <span class="ant-select-selection-item">host-a</span>
          <span class="ant-select-selection-item">+2</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium">时间范围:</span>
        <div class="ant-select-selection-item">自定义</div>
        <div class="ant-picker">
          <div class="ant-picker-input"><input value="2026-09-01 00:00:00" /></div>
          <div class="ant-picker-input"><input value="2026-09-07 23:59:59" /></div>
        </div>
      </div>
    `);
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('对象: host-a、+2');
    expect(readOpsAnalysisDashboardStamp().filterText).toContain('2026-09-01 00:00:00 ~ 2026-09-07 23:59:59');
  });
});

describe('ops-analysis dashboard.pilot screenshot eligibility', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setView('?type=dashboard&id=dash-1');
  });

  it('skips sparkline and short nodes, keeps titled line charts, and takes 6 in reading order', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget" data-chart="spark">
        <div class="widget">
          <div class="widget-header"><h4>CPU 当前</h4></div>
          <div class="widget-body">
            <span class="font-semibold">86%</span>
            <div _echarts_instance_="spark"></div>
          </div>
        </div>
      </div>
      ${[1, 2, 3, 4, 5, 6, 7].map((index) => `
        <div data-node-kind="widget" data-chart="line-${index}">
          <div class="widget">
            <div class="widget-header"><h4>趋势 ${index}</h4></div>
            <div class="widget-body"><div _echarts_instance_="line-${index}"></div></div>
          </div>
        </div>
      `).join('')}
    `);
    const spark = document.querySelector<HTMLElement>('[_echarts_instance_="spark"]')!;
    stubRect(spark, { height: 40, top: 0, left: 0 });
    const lines = Array.from(document.querySelectorAll<HTMLElement>('[_echarts_instance_^="line-"]'));
    lines.forEach((node, index) => {
      stubRect(node, { height: 180, top: index < 4 ? 10 : 400, left: (index % 4) * 200 });
    });
    expect(isDecorativeOpsAnalysisChart(spark)).toBe(true);
    expect(lines.every((node) => !isDecorativeOpsAnalysisChart(node))).toBe(true);
    const shot = listScreenshotableChartDoms();
    expect(shot).toHaveLength(6);
    expect(shot.map((node) => node.getAttribute('_echarts_instance_'))).toEqual([
      'line-1',
      'line-2',
      'line-3',
      'line-4',
      'line-5',
      'line-6',
    ]);
  });
});

describe('ops-analysis dashboard.pilot text context', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    setView('?type=dashboard&id=dash-1');
  });

  it('includes visible card names, single values, and at most 10 table/TopN rows', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div class="flex items-center gap-2">
        <span class="text-xs font-medium tracking-[0.02em]">对象:</span>
        <div class="ant-select-selection-item">host-a</div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>CPU 使用率</h4></div>
          <div class="widget-body"><span class="font-semibold">82.9%</span></div>
        </div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>主机排行</h4></div>
          <div class="widget-body">
            <div class="grid items-center rounded-md font-medium">
              <span>名称</span><span></span><span class="text-right">值</span>
            </div>
            <div class="grid items-center">
              <span>host-a</span><div class="h-2.5 w-full overflow-hidden rounded-full"></div><span class="font-semibold tabular-nums">92</span>
              <span>host-b</span><div class="h-2.5 w-full overflow-hidden rounded-full"></div><span class="font-semibold tabular-nums">80</span>
            </div>
          </div>
        </div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>事件表</h4></div>
          <div class="widget-body">
            <table>
              <thead><tr><th>主机</th><th>次数</th></tr></thead>
              <tbody class="ant-table-tbody">
                ${Array.from({ length: 12 }, (_, index) => `<tr><td>row-${index + 1}</td><td>${index + 1}</td></tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('生产总览');
    expect(text).toContain('对象: host-a');
    expect(text).toContain('CPU 使用率');
    expect(text).toContain('82.9%');
    expect(text).toContain('主机排行');
    expect(text).toContain('host-a');
    expect(text).toContain('92');
    expect(text).not.toMatch(/名称\s+值/);
    expect(text).toContain('事件表');
    expect(text).toContain('主机');
    expect(text).toContain('row-10');
    expect(text).not.toContain('row-11');
  });

  it('keeps identity and filters when table rows exceed the text budget', () => {
    setView('?type=dashboard&id=dash-1');
    const hugeRows = Array.from({ length: 10 }, (_, index) => `row-${index}:${'x'.repeat(900)}`).join('\n');
    const context = {
      sections: [
        { id: 'dashboard-identity', label: '当前仪表盘', content: '盘名: 生产总览\n当前筛选: 时间: 最近6小时', priority: 10 },
        { id: 'dashboard-cards', label: '可见卡片', content: 'CPU 使用率: 82.9%', priority: 8 },
        { id: 'visible-charts', label: '可见图表', content: '1. CPU 趋势', priority: 6 },
        { id: 'dashboard-tables', label: '表与排行', content: hugeRows, priority: 4 },
      ],
    };
    const merged = mergePageContexts([context]);
    const kept = (merged.sections || []).map((section) => section.id);
    expect(kept).toContain('dashboard-identity');
    expect((merged.sections || []).some((section) => section.content.includes('生产总览'))).toBe(true);
    expect((merged.sections || []).reduce((sum, section) => sum + section.content.length, 0)).toBeLessThanOrEqual(
      PAGE_CONTEXT_TEXT_BUDGET,
    );
  });

  it('skips loading cards for numbers and screenshots and reports how many are not ready', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>加载中的卡</h4></div>
          <div class="widget-body">
            <div class="ant-spin ant-spin-spinning"></div>
            <span class="font-semibold">0</span>
            <div _echarts_instance_="loading-line"></div>
          </div>
        </div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>已就绪</h4></div>
          <div class="widget-body"><span class="font-semibold">12</span></div>
        </div>
      </div>
    `);
    const loadingChart = document.querySelector<HTMLElement>('[_echarts_instance_="loading-line"]')!;
    stubRect(loadingChart, { height: 180, top: 0, left: 0 });
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('加载中的卡: 加载中');
    expect(text).toContain('已就绪');
    expect(text).toContain('12');
    expect(text).toMatch(/还有\s*1\s*个组件未加载完/);
    expect(text).not.toMatch(/加载中的卡[\s\S]*:\s*0/);
    expect(listScreenshotableChartDoms()).toHaveLength(0);
  });

  it('passes query-failed and empty widget copy instead of treating the card as a blank number', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>CPU 使用率趋势</h4></div>
          <div class="widget-body">
            <div class="flex h-full flex-col items-center justify-center">
              <span class="anticon anticon-exclamation-circle"></span>
              <span>主机指标查询失败</span>
            </div>
            <div _echarts_instance_="failed-line"></div>
          </div>
        </div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>磁盘</h4></div>
          <div class="widget-body">
            <div class="ant-empty"><div class="ant-empty-description">暂无数据</div></div>
          </div>
        </div>
      </div>
    `);
    const failedChart = document.querySelector<HTMLElement>('[_echarts_instance_="failed-line"]')!;
    stubRect(failedChart, { height: 180, top: 0, left: 0 });
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('CPU 使用率趋势: 主机指标查询失败');
    expect(text).toContain('磁盘: 暂无数据');
    expect(text).toMatch(/有\s*1\s*个组件查询失败/);
    expect(listScreenshotableChartDoms()).toHaveLength(0);
  });

  it('copies multi-value rows and card-list items instead of only the first number', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>资源概览</h4></div>
          <div class="widget-body">
            <div class="flex min-w-0 items-center justify-between"><span>平均 CPU</span><span class="font-semibold">12%</span></div>
            <div class="flex min-w-0 items-center justify-between"><span>平均内存</span><span class="font-semibold">40%</span></div>
          </div>
        </div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>告警列表</h4></div>
          <div class="widget-body">
            <article>
              <div class="text-sm font-medium">host-a 告警</div>
              <span class="text-xs font-medium">critical</span>
              <span class="text-xs font-medium">12</span>
            </article>
            <article>
              <div class="text-sm font-medium">host-b 告警</div>
              <span class="text-xs font-medium">warning</span>
              <span class="text-xs font-medium">3</span>
            </article>
          </div>
        </div>
      </div>
    `);
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('平均 CPU 12%');
    expect(text).toContain('平均内存 40%');
    expect(text).toContain('host-a 告警 12');
    expect(text).toContain('host-b 告警 3');
    expect(text).not.toMatch(/host-a 告警 critical/);
  });

  it('changes currentTime when multi-value rows change', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>资源概览</h4></div>
          <div class="widget-body">
            <div class="flex min-w-0 items-center justify-between"><span>平均 CPU</span><span class="font-semibold">12%</span></div>
            <div class="flex min-w-0 items-center justify-between"><span>平均内存</span><span class="font-semibold">40%</span></div>
          </div>
        </div>
      </div>
    `);
    const first = buildOpsAnalysisCurrentTime(readOpsAnalysisDashboardStamp());
    document.querySelectorAll('.font-semibold')[1]!.textContent = '55%';
    const changed = buildOpsAnalysisCurrentTime(readOpsAnalysisDashboardStamp());
    expect(changed).not.toBe(first);
  });

  it('drops the generic chart caption placeholder when filling widget titles', async () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>数据治理健康度趋势</h4></div>
          <div class="widget-body"><div _echarts_instance_="line-1"></div></div>
        </div>
      </div>
    `);
    const chart = document.querySelector<HTMLElement>('[_echarts_instance_="line-1"]')!;
    stubRect(chart, { height: 180, top: 0, left: 0 });
    const toolkit: PageContextToolkit = {
      captureEchartsFromDoms: async () => [{
        dataUrl: 'data:image/jpeg,x',
        caption: '图表；序列: 数据治理健康度, CMDB 数据完整率, 数据滞后率; 最新值: 2.2, 26.2, 3.8',
      }],
      captureEchartsFromDom: async () => [],
      captionFromOption: () => '图表',
    };
    const full = await getContext(toolkit);
    const captions = (full.images || []).map((image) => image.caption).join('\n');
    const chartSection = (full.sections || []).find((section) => section.id === 'visible-charts')?.content || '';
    expect(captions).toContain('数据治理健康度趋势');
    expect(captions).toContain('最新值: 2.2, 26.2, 3.8');
    expect(captions).not.toMatch(/^图表；/);
    expect(captions).not.toContain('图表；序列');
    expect(chartSection).toContain('数据治理健康度趋势');
    expect(chartSection).not.toMatch(/1\.\s*图表；/);
  });

  it('skips widgets hidden by a collapsed group', () => {
    setView('?type=dashboard&id=dash-1');
    document.body.innerHTML = dashboardShell(`
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>折叠卡</h4></div>
          <div class="widget-body" style="display:none">
            <span class="font-semibold">99</span>
            <div _echarts_instance_="folded"></div>
          </div>
        </div>
      </div>
      <div data-node-kind="widget">
        <div class="widget">
          <div class="widget-header"><h4>可见卡</h4></div>
          <div class="widget-body"><span class="font-semibold">12</span></div>
        </div>
      </div>
    `);
    const folded = document.querySelector<HTMLElement>('[_echarts_instance_="folded"]')!;
    stubRect(folded, { height: 180, top: 0, left: 0 });
    const text = (getTextContext().sections || []).map((section) => section.content).join('\n');
    expect(text).toContain('可见卡');
    expect(text).toContain('12');
    expect(text).not.toContain('折叠卡');
    expect(text).not.toContain('99');
    expect(listScreenshotableChartDoms()).toHaveLength(0);
  });

  it('keeps the dashboard name on an empty board and does not invent images', async () => {
    setView('?type=dashboard&id=dash-empty');
    document.body.innerHTML = dashboardShell('');
    const text = getTextContext();
    expect((text.sections || []).some((section) => section.content.includes('生产总览'))).toBe(true);
    expect(text.images || []).toEqual([]);
    const toolkit: PageContextToolkit = {
      captureEchartsFromDoms: async () => [{ dataUrl: 'data:image/jpeg,x', caption: '不该出现' }],
      captureEchartsFromDom: async () => [],
      captionFromOption: () => '',
    };
    const full = await getContext(toolkit);
    expect(full.images || []).toEqual([]);
  });
});
