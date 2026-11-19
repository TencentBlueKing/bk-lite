import type { ReactNode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MetricSeries } from '../../../common/simple-dashboard-core';
import { toMetricSeries } from '../../../../shared/utils/metric-series';
import { dashboardQueryCapabilityId } from '../../../../shared/utils/query-capability';
import { ProTimeWindowProvider } from '../../../host/layered/pro-time-window';
import { MSSQL_TOP_DB_QUERIES } from '../../queries';
import BufferPane from '../buffer-pane';
import IoPane from '../io-pane';
import OverviewPane from '../overview-pane';
import { MSSQL_PRO_METRICS, MSSQL_PRO_NAMES } from '../queries';

const query = vi.hoisted(() => vi.fn());
const seen = vi.hoisted(() => ({
  options: [] as Array<Record<string, any> | null>
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, status: 'unauthenticated' })
}));

vi.mock('@/app/monitor/api/view', () => ({
  default: () => ({ getInstanceQuery: query })
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

const load = (name: string, samples: Array<[number, string]>) => toMetricSeries(
  metric(name),
  { data: { result: [{ metric: { instance_id: 'inst' }, values: samples }] } },
  'inst',
  '10.10.90.113:1433',
  ['inst'],
  ['instance_id']
);

const clerkSeries = (points: MetricSeries['viewData']): MetricSeries => ({
  name: 'mssql_pro_clerks',
  display_name: 'mssql_pro_clerks',
  description: '',
  unit: 'kibibytes',
  query: '',
  color: '#000',
  viewData: points,
  loadState: 'success'
});

const WINDOW_START = 1_700_000_000_000;
const WINDOW_END = 1_700_000_900_000;

function mount(node: ReactNode) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

function overview(alertCount: number) {
  return mount(
    <ProTimeWindowProvider
      timeValues={{ timeRange: [WINDOW_START, WINDOW_END], originValue: 15 }}
      queryTimeRange={{ startMs: WINDOW_START, endMs: WINDOW_END }}
    >
      <OverviewPane
        metricMap={{
          [MSSQL_PRO_NAMES.readLatency]: load(MSSQL_PRO_NAMES.readLatency, [[1_700_000_000, '6448']])
        }}
        pendingMetricNames={new Set()}
        booting={false}
        alertCount={alertCount}
        alertsOpen={false}
        alertEvents={[{
          id: 'alert-14',
          alertId: 'alert-14',
          at: '2020-01-01T00:00:00.000Z',
          action: 'triggered',
          level: 'warning',
          status: 'new',
          summary: '磁盘读取变慢',
          detail: '读取延迟升高'
        }]}
        onOpenAlerts={() => undefined}
        onOpenFocus={() => undefined}
        onFocusAlert={() => undefined}
      />
    </ProTimeWindowProvider>
  );
}

describe('mssql display face', () => {
  beforeEach(() => {
    seen.options.length = 0;
    query.mockReset();
    query.mockImplementation(async (params: { capability_id?: string }) => {
      const key = MSSQL_TOP_DB_QUERIES.find(
        (item) => dashboardQueryCapabilityId(item.query) === params.capability_id
      )?.key;
      if (key === 'read_latency') {
        return {
          data: {
            result: [
              { metric: { database_name: 'tempdb' }, values: [[1, '96000']] },
              { metric: { database_name: 'master' }, values: [[1, '1200']] }
            ]
          }
        };
      }
      if (key === 'write_latency') {
        return {
          data: {
            result: [{ metric: { database_name: 'tempdb' }, values: [[1, '800']] }]
          }
        };
      }
      return {
        data: {
          result: [
            { metric: { database_name: 'tempdb' }, values: [[1, '0.23']] },
            { metric: { database_name: 'model' }, values: [[1, '0']] }
          ]
        }
      };
    });
  });

  it('告警数量大于 0 时，窗外的活跃告警仍出现在健康概览和重点关注之间', () => {
    const view = overview(14);
    const pane = view.container.querySelector('[data-mssql-pane="overview"]');
    const headings = Array.from(pane?.querySelectorAll(':scope > section') || []).map(
      (section) => section.querySelector(':scope > div')?.textContent || ''
    );
    expect(headings[0]).toContain('健康概览');
    expect(headings[1]).toContain('事件');
    expect(headings[2]).toContain('重点关注');
    expect(view.container.querySelector('[data-events-rail]')).toBeTruthy();
    expect(view.container.textContent).toContain('磁盘读取变慢');
    expect(view.container.querySelector('[data-events-empty]')).toBeNull();
    const latency = view.container.querySelector('[data-mssql-focus="read-latency"]');
    expect(latency?.textContent).toContain('6.45 s');
    expect(latency?.textContent).not.toContain('6.448');
  });

  it('没有告警时不渲染事件条', () => {
    const view = overview(0);
    expect(view.container.querySelector('[data-events-rail]')).toBeNull();
    expect(view.container.textContent).not.toContain('磁盘读取变慢');
    const pane = view.container.querySelector('[data-mssql-pane="overview"]');
    const headings = Array.from(pane?.querySelectorAll(':scope > section') || []).map(
      (section) => section.querySelector(':scope > div')?.textContent || ''
    );
    expect(headings[1]).toContain('重点关注');
    const alerts = view.container.querySelector('[data-kpi="alert-count"]');
    expect(alerts?.textContent).toContain('告警数量');
    expect(alerts?.textContent).not.toContain('告警事件');
    expect(alerts?.textContent).not.toContain('0 个');
    expect(alerts?.textContent).not.toContain('(个)');
  });

  it('内存用途构成把色点和同色读数放进白卡，并保留源端维度名', () => {
    const view = mount(
      <BufferPane
        metricMap={{
          mssql_pro_clerks: clerkSeries([{
            time: 1,
            value1: 1024 * 1024,
            value2: 512 * 1024,
            seriesMetrics: {
              value1: { clerk_type: 'SOS Node' },
              value2: { clerk_type: 'Buffer Pool' }
            }
          } as never])
        }}
        pendingMetricNames={new Set()}
      />
    );
    expect(view.container.textContent).toContain('内存用途构成');
    expect(view.container.textContent).not.toContain('内存 Clerk 构成');
    const chart = view.container.querySelector('[data-mssql-chart="clerks"]');
    const side = chart?.querySelector('[data-mssql-side-readout]');
    const section = side?.querySelector('section');
    const frame = side?.querySelector('[data-mssql-series-frame]');
    const list = frame?.querySelector('[data-mssql-series-readout]');
    expect(side?.className).toContain('220px');
    expect(side?.className).toContain('gap-4');
    expect(list).toBeTruthy();
    expect(section?.contains(list || null)).toBe(false);
    expect(frame?.parentElement).not.toBe(section);
    expect(frame?.className).toContain('border');
    expect(frame?.className).toContain('bg-[var(--color-bg)]');
    expect(list?.className).toContain('bg-[var(--color-bg)]');
    expect(section?.getAttribute('style') || section?.querySelector('[class*="chartBody"]')?.getAttribute('style')).toContain('132px');
    const row = view.getByText('SOS Node').closest('li');
    const swatch = row?.querySelector('[data-mssql-readout-swatch]');
    const value = row?.querySelector('[data-mssql-readout-value]');
    expect(row?.textContent).toContain('SOS Node');
    expect(view.getByText('Buffer Pool')).toBeTruthy();
    expect(swatch?.getAttribute('style')).toBeTruthy();
    expect(value?.style.color).toBe(swatch?.style.backgroundColor);
    expect(value?.textContent).not.toMatch(/\.\d{3}/);
  });

  it('压力排行三组同时可见，TempDB 两条 MiB 序列共用左轴', async () => {
    const view = mount(
      <IoPane
        metricMap={{
          [MSSQL_PRO_NAMES.tempdbFree]: load(
            MSSQL_PRO_NAMES.tempdbFree,
            [[1_700_000_000, String(45 * 1024)], [1_700_000_060, String(45 * 1024)]]
          ),
          [MSSQL_PRO_NAMES.versionStore]: load(
            MSSQL_PRO_NAMES.versionStore,
            [[1_700_000_000, '0'], [1_700_000_060, '0']]
          )
        }}
        pendingMetricNames={new Set()}
        instanceId="1"
        monitorObjectId="1"
        idValues={['inst']}
        instanceIdKeys={['instance_id']}
        timeValues={{ timeRange: [WINDOW_START, WINDOW_END], originValue: 15 }}
        reloadKey={1}
      />
    );
    const tempdb = view.container.querySelector('[data-mssql-chart="tempdb"]');
    expect(tempdb?.getAttribute('data-mssql-axes')).toBe('shared');
    const option = seen.options.find((item) => {
      const names = (item?.series || []).map((series: { name?: string }) => series.name);
      return names.includes('可用空间') && names.includes('版本存储');
    });
    expect(option).toBeTruthy();
    expect(Array.isArray(option?.yAxis)).toBe(false);
    const version = (option?.series || []).find((series: { name?: string }) => series.name === '版本存储');
    expect(version?.yAxisIndex).toBeUndefined();
    expect(version?.lineStyle?.color).toBe(version?.itemStyle?.color);
    expect(view.container.querySelector('.ant-segmented')).toBeNull();
    const rankRow = view.container.querySelector('[data-mssql-rank-groups]');
    expect(rankRow?.getAttribute('data-mssql-rank-groups')).toBe('3');
    expect(rankRow?.getAttribute('data-mssql-rank-layout')).toBe('cards');
    expect(rankRow?.tagName).toBe('DIV');
    await waitFor(() => {
      expect(view.container.querySelector('[data-mssql-rank="read_latency"]')?.textContent).toContain('1.60 min');
    });
    const read = view.container.querySelector('[data-mssql-rank="read_latency"]');
    const write = view.container.querySelector('[data-mssql-rank="write_latency"]');
    const busy = view.container.querySelector('[data-mssql-rank="io_rate"]');
    expect(read?.tagName).toBe('SECTION');
    expect(write?.tagName).toBe('SECTION');
    expect(busy?.tagName).toBe('SECTION');
    expect(read?.parentElement).toBe(rankRow);
    expect(write?.parentElement).toBe(rankRow);
    expect(busy?.parentElement).toBe(rankRow);
    expect(read?.getAttribute('aria-label') || read?.querySelector('[aria-label]')?.getAttribute('aria-label')).toContain('读得慢的库');
    expect(write?.querySelector('[aria-label]')?.getAttribute('aria-label')).toContain('写得慢的库');
    expect(busy?.querySelector('[aria-label]')?.getAttribute('aria-label')).toContain('每秒读写次数');
    expect(read?.textContent).toContain('读取延迟');
    expect(read?.textContent).toContain('tempdb');
    expect(read?.textContent).toContain('0.02 min');
    expect(write?.textContent).toContain('写入延迟');
    expect(write?.textContent).toContain('800 ms');
    expect(busy?.textContent).toContain('读写繁忙');
    expect(busy?.textContent).toContain('0.23/s');
    expect(busy?.textContent).toContain('0/s');
    expect(busy?.textContent).not.toContain('0.00');
    expect(busy?.textContent).not.toContain(' min');
    expect(busy?.textContent).not.toContain(' ms');
  });
});
