import type { ReactNode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WaitsPane from '../waits-pane';

const query = vi.hoisted(() => vi.fn());

vi.mock('@/app/monitor/api/view', () => ({
  default: () => ({ getInstanceQuery: query })
}));

vi.mock('../../../../shared/widgets/useECharts', () => ({
  useECharts: () => ({ containerRef: () => undefined, getInstance: () => null })
}));

const named = ['Memory', 'Preemptive', 'Buffer IO', 'CPU', 'Network IO', 'Lock', 'Latch', '类别8'];
const categories = named.map((waitCategory, index) => ({
  metric: { wait_category: waitCategory },
  values: [[1_700_000_000, String((index + 1) * 10)], [1_700_000_060, String((index + 1) * 10)]]
}));

function mount(node: ReactNode) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

describe('mssql waits layout', () => {
  beforeEach(() => {
    query.mockReset();
    query.mockResolvedValue({ data: { result: categories } });
  });

  it('锁等待、阻塞进程数、死锁次数分成三张卡，等待类别 Top 是左图右读数栏', async () => {
    const view = mount(
      <WaitsPane
        metricMap={{}}
        pendingMetricNames={new Set()}
        instanceId="1"
        monitorObjectId="1"
        idValues={['inst']}
        instanceIdKeys={['instance_id']}
        timeValues={{ timeRange: [1, 2], originValue: 15 }}
        reloadKey={1}
      />
    );
    expect(view.container.querySelector('[data-mssql-chart="locks"]')).toBeTruthy();
    expect(view.container.querySelector('[data-mssql-chart="blocked"]')).toBeTruthy();
    expect(view.container.querySelector('[data-mssql-chart="deadlocks"]')).toBeTruthy();
    expect(view.container.textContent).toContain('锁等待');
    expect(view.container.textContent).toContain('阻塞进程数');
    expect(view.container.textContent).toContain('死锁次数');
    expect(view.container.textContent).not.toContain('锁等待与阻塞');
    const mix = view.container.querySelector('[data-mssql-chart="wait-mix"]');
    const top = view.container.querySelector('[data-mssql-chart="wait-top"]');
    expect(mix?.parentElement).not.toBe(top?.parentElement);
    await waitFor(() => {
      expect(top?.querySelector('[data-mssql-side-readout]')).toBeTruthy();
    });
    const frame = top?.querySelector('[data-mssql-series-frame]');
    const plot = top?.querySelector('section');
    expect(plot?.contains(frame || null)).toBe(false);
    expect(top?.querySelectorAll('[data-mssql-series-readout] li')).toHaveLength(8);
    expect(top?.textContent).toContain('内存');
    expect(top?.textContent).toContain('抢占');
    expect(top?.textContent).toContain('缓冲读写');
    expect(top?.textContent).toContain('处理器');
    expect(top?.textContent).toContain('网络读写');
    expect(top?.textContent).toContain('ms/s');
    expect(top?.textContent).not.toContain('Memory');
    expect(top?.textContent).not.toContain('Preemptive');
    expect(top?.textContent).not.toContain('Buffer IO');
    expect(top?.textContent).not.toContain('CPU');
    expect(top?.textContent).not.toContain('Network IO');
    expect(top?.textContent).not.toContain(' min');
  });
});
