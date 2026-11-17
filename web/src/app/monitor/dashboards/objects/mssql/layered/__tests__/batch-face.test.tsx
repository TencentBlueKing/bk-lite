import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { describe, expect, it, vi } from 'vitest';
import { toMetricSeries } from '../../../../shared/utils/metric-series';
import OverviewPane from '../overview-pane';
import { MSSQL_PRO_METRICS, MSSQL_PRO_NAMES } from '../queries';
import { mssqlLatest } from '../series';

const seen = vi.hoisted(() => ({
  options: [] as Array<Record<string, any> | null>
}));

vi.mock('../../../../shared/widgets/useECharts', () => ({
  useECharts: (option: Record<string, any> | null) => {
    seen.options.push(option);
    return { containerRef: () => undefined, getInstance: () => null };
  }
}));

const metric = (name: string) => {
  const found = MSSQL_PRO_METRICS.find((item) => item.name === name);
  if (!found) throw new Error(`missing metric ${name}`);
  return found;
};

const range = (samples: Array<[number, string]>) => ({
  data: {
    result: samples.length
      ? [{ metric: { instance_id: 'OGNkZGVhNmJhYWFi' }, values: samples }]
      : []
  }
});

const load = (name: string, samples: Array<[number, string]>) => toMetricSeries(
  metric(name),
  range(samples),
  'OGNkZGVhNmJhYWFi',
  '10.10.90.113:1433',
  ['OGNkZGVhNmJhYWFi'],
  ['instance_id']
);

const ZEROS: Array<[number, string]> = [[1_700_000_000, '0'], [1_700_000_060, '0']];

function mount(node: ReactNode) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

describe('mssql batch face', () => {
  it('进程 CPU 的 0 从查询结果进到 KPI 和 0–100 可见零值线', () => {
    seen.options.length = 0;
    const cpu = load(MSSQL_PRO_NAMES.processCpu, ZEROS);
    const idle = load(MSSQL_PRO_NAMES.idleCpu, []);
    expect(mssqlLatest({ [cpu.name]: cpu }, cpu.name)).toBe(0);
    expect(cpu.viewData.every((point) => point.value1 === 0)).toBe(true);
    const view = mount(
      <OverviewPane
        metricMap={{ [cpu.name]: cpu, [idle.name]: idle }}
        pendingMetricNames={new Set()}
        booting={false}
        batchLoading={false}
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        onOpenAlerts={() => undefined}
        onOpenFocus={() => undefined}
        onFocusAlert={() => undefined}
      />
    );
    const kpi = view.container.querySelector('[data-kpi="cpu"]');
    expect(kpi?.textContent).toContain('0%');
    expect(kpi?.textContent).not.toContain('加载中');
    expect(kpi?.textContent).not.toContain('—');
    const chart = view.container.querySelector('[data-mssql-chart="cpu"]');
    expect(chart?.getAttribute('data-mssql-face')).toBe('ready');
    expect(chart?.textContent).not.toContain('本窗口暂无数据');
    const option = seen.options.find((item) => (
      Array.isArray(item?.series)
      && item.series.some((series: { name?: string }) => series.name === '进程 CPU')
    ));
    expect(option).toBeTruthy();
    expect(option?.yAxis?.min).toBe(0);
    expect(option?.yAxis?.max).toBe(100);
    const process = option?.series.find((series: { name?: string }) => series.name === '进程 CPU');
    expect(process?.showSymbol).toBe(true);
    expect(process?.data?.some((point: [number, number | null]) => point[1] === 0)).toBe(true);
  });

  it('同一批还没结束时，没点的焦点保持加载；已经回来的 0 照常显示', () => {
    const cpu = load(MSSQL_PRO_NAMES.processCpu, ZEROS);
    const blocked = load(MSSQL_PRO_NAMES.blocked, ZEROS);
    const pending = new Set([MSSQL_PRO_NAMES.deadlocks]);
    const open = mount(
      <OverviewPane
        metricMap={{ [cpu.name]: cpu, [blocked.name]: blocked }}
        pendingMetricNames={pending}
        booting={false}
        batchLoading
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        onOpenAlerts={() => undefined}
        onOpenFocus={() => undefined}
        onFocusAlert={() => undefined}
      />
    );
    expect(open.container.querySelector('[data-kpi="cpu"]')?.textContent).toContain('0%');
    const blockedCard = open.container.querySelector('[data-mssql-focus="blocked"]');
    expect(blockedCard?.getAttribute('data-mssql-face')).toBe('ready');
    expect(blockedCard?.textContent).toContain('0 个');
    const latency = open.container.querySelector('[data-mssql-focus="read-latency"]');
    const deadlocks = open.container.querySelector('[data-mssql-focus="deadlocks"]');
    expect(latency?.getAttribute('data-mssql-face')).toBe('loading');
    expect(deadlocks?.getAttribute('data-mssql-face')).toBe('loading');
    expect(latency?.textContent).toContain('加载中');
    expect(latency?.textContent).not.toContain('—');
    expect(open.container.querySelector('[data-mssql-chart="cpu"]')?.getAttribute('data-mssql-face')).toBe('ready');
    expect(open.container.querySelector('[data-mssql-chart="connections"]')?.getAttribute('data-mssql-face')).toBe('loading');
    expect(open.container.querySelector('[data-mssql-chart="connections"]')?.textContent).not.toContain('本窗口暂无数据');
    open.unmount();

    const waiting = mount(
      <OverviewPane
        metricMap={{
          [load(MSSQL_PRO_NAMES.connections, [[1_700_000_000, '36']]).name]: load(MSSQL_PRO_NAMES.connections, [[1_700_000_000, '36']])
        }}
        pendingMetricNames={pending}
        booting={false}
        batchLoading
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        onOpenAlerts={() => undefined}
        onOpenFocus={() => undefined}
        onFocusAlert={() => undefined}
      />
    );
    const waitingCpu = waiting.container.querySelector('[data-kpi="cpu"]');
    expect(waitingCpu?.textContent).toContain('加载中');
    expect(waitingCpu?.textContent).not.toContain('—');
    expect(waiting.container.querySelector('[data-kpi="connections"]')?.textContent).toContain('36');
    expect(waiting.container.querySelector('[data-mssql-chart="cpu"]')?.getAttribute('data-mssql-face')).toBe('loading');
    expect(waiting.container.querySelector('[data-mssql-chart="cpu"]')?.textContent).not.toContain('本窗口暂无数据');
    waiting.unmount();

    const settled = mount(
      <OverviewPane
        metricMap={{}}
        pendingMetricNames={new Set()}
        booting={false}
        batchLoading={false}
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        onOpenAlerts={() => undefined}
        onOpenFocus={() => undefined}
        onFocusAlert={() => undefined}
      />
    );
    const settledLatency = settled.container.querySelector('[data-mssql-focus="read-latency"]');
    const settledCpu = settled.container.querySelector('[data-mssql-chart="cpu"]');
    expect(settledLatency?.getAttribute('data-mssql-face')).toBe('empty');
    expect(settledLatency?.textContent).toContain('—');
    expect(settledLatency?.querySelector('[data-pro-dash-loading]')).toBeNull();
    expect(settledCpu?.getAttribute('data-mssql-face')).toBe('empty');
    expect(settledCpu?.textContent).toContain('本窗口暂无数据');
    expect(settledCpu?.querySelector('[data-pro-dash-loading]')).toBeNull();
    expect(settled.container.querySelector('[data-kpi="cpu"]')?.textContent).toContain('—');
    expect(settled.container.querySelector('[data-kpi="cpu"]')?.querySelector('[data-pro-dash-loading]')).toBeNull();
  });
});
