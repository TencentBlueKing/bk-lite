import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { describe, expect, it } from 'vitest';
import type { MetricSeries } from '../../../common/simple-dashboard-core';
import { markedZeroSeries } from '../../../host/layered/thin-time-series';
import BufferPane from '../buffer-pane';
import { MSSQL_TABS, resolveMssqlTab } from '../ia';
import {
  clerkChart,
  formatPercentPoint,
  mssqlCountAxisBounds,
  mssqlCountMerged,
  mssqlLatest,
  mssqlPoints,
  mssqlSamplesAreFlatZero,
  type MssqlMetricMap
} from '../series';

const series = (
  name: string,
  points: MetricSeries['viewData']
): MetricSeries => ({
  name,
  display_name: name,
  description: '',
  unit: 'percent',
  query: '',
  color: '#000',
  viewData: points,
  loadState: 'success'
});

function mount(locale: string, messages: Record<string, string>, node: ReactNode) {
  return render(<IntlProvider locale={locale} messages={messages}>{node}</IntlProvider>);
}

describe('mssql empty shell口径', () => {
  it('进程 CPU 有点全 0 记成 0%，零值点留下来，空的对照序列不取消零值线', () => {
    expect(formatPercentPoint(0)).toBe('0%');
    expect(formatPercentPoint(100)).toBe('100.0%');
    const map: MssqlMetricMap = {
      mssql_pro_process_cpu: series('mssql_pro_process_cpu', [
        { time: 1_700_000_000, value1: 0 },
        { time: 1_700_000_060, value1: '0' as unknown as number }
      ]),
      mssql_pro_idle_cpu: series('mssql_pro_idle_cpu', [])
    };
    expect(mssqlLatest(map, 'mssql_pro_process_cpu')).toBe(0);
    expect(mssqlPoints(map, 'mssql_pro_process_cpu')).toHaveLength(2);
    expect(mssqlSamplesAreFlatZero([0, 0])).toBe(true);
    expect(mssqlSamplesAreFlatZero([])).toBe(false);
    expect(markedZeroSeries(true, [0, 0])).toBe(true);
    expect(markedZeroSeries(true, [])).toBe(false);
    expect(mssqlCountAxisBounds([0, 0])).toEqual({ min: 0, max: 4 });
  });

  it('死锁有点全 0 时，概览焦点和等待签用同一组点、同一软顶', () => {
    const map: MssqlMetricMap = {
      mssql_pro_deadlocks_count: series('mssql_pro_deadlocks_count', [
        { time: 10, value1: 0 },
        { time: 20, value1: 0 }
      ])
    };
    const plotted = mssqlCountMerged(map, [{ name: 'mssql_pro_deadlocks_count', label: '死锁次数' }]);
    const samples = plotted.map((point) => Number(point.value1));
    expect(plotted).toHaveLength(2);
    expect(samples).toEqual([0, 0]);
    expect(mssqlCountAxisBounds(samples)).toEqual({ min: 0, max: 4 });
    expect(markedZeroSeries(true, samples)).toBe(true);
    expect(mssqlLatest({}, 'mssql_pro_deadlocks_count')).toBeNull();
  });

  it('Clerk 有数但没有类型标签时仍出线，没有点不造列表', () => {
    const drawn = clerkChart({
      mssql_pro_clerks: series('mssql_pro_clerks', [{ time: 10, value1: 282648 }])
    });
    expect(drawn.data.length).toBeGreaterThan(0);
    expect(drawn.legends.map((item) => item.label)).toEqual(['内存占用']);

    const empty = clerkChart({});
    expect(empty.data).toEqual([]);
    expect(empty.legends).toEqual([]);
  });

  it('只留四个必做签，旧的 Top SQL 和复制地址回到概览', () => {
    expect(MSSQL_TABS.map((tab) => tab.key)).toEqual(['overview', 'buffer_memory', 'io_storage', 'waits']);
    expect(resolveMssqlTab('top_sql')).toBe('overview');
    expect(resolveMssqlTab('replication')).toBe('overview');
  });

  it('内存卡标题和问号都叫实例内存，英文是 Instance Memory', () => {
    const zh = mount('zh', {}, <BufferPane metricMap={{}} pendingMetricNames={new Set()} />);
    expect(zh.container.textContent).toContain('实例内存');
    expect(zh.container.textContent).toContain('当前');
    expect(zh.container.textContent).toContain('目标');
    expect(zh.container.textContent).toContain('内存');
    expect(zh.container.textContent).not.toContain('Server Memory');
    expect(zh.container.textContent).not.toContain('服务器内存');
    zh.unmount();

    const en = mount('en', {
      'monitor.dashboards.text.mssqlInstanceMemory': 'Instance Memory',
      'monitor.dashboards.text.mssqlInstanceMemoryBody': 'Memory currently committed to SQL Server.',
      'monitor.dashboards.text.mssqlMemoryCurrent': 'Current',
      'monitor.dashboards.text.mssqlMemoryTarget': 'Target'
    }, <BufferPane metricMap={{}} pendingMetricNames={new Set()} />);
    expect(en.container.textContent).toContain('Instance Memory');
    expect(en.container.textContent).toContain('Current');
    expect(en.container.textContent).toContain('Target');
    expect(en.container.textContent).not.toContain('Server Memory');
    expect(en.container.textContent).not.toContain('实例内存');
  });
});
