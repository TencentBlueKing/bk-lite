import type { ReactNode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MSSQL_WAIT_TOP_VIEWPORT } from '../display-units';
import WaitsPane from '../waits-pane';

const query = vi.hoisted(() => vi.fn());

vi.mock('@/app/monitor/api/view', () => ({
  default: () => ({ getInstanceQuery: query })
}));

vi.mock('../../../../shared/widgets/useECharts', () => ({
  useECharts: () => ({ containerRef: () => undefined, getInstance: () => null })
}));

const categories = Array.from({ length: 8 }, (_, index) => ({
  metric: { wait_category: `类别${index + 1}` },
  values: [[1_700_000_000, String((index + 1) * 1000)]]
}));

function mount(node: ReactNode) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

describe('mssql waits layout', () => {
  beforeEach(() => {
    query.mockReset();
    query.mockResolvedValue({ data: { result: categories } });
  });

  it('锁等待、阻塞进程数、死锁次数分成三张卡，Top 按 5 行高度滚动', async () => {
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
    const viewport = view.container.querySelector('[data-mssql-wait-viewport]');
    expect(viewport?.getAttribute('style')).toContain(`height: ${MSSQL_WAIT_TOP_VIEWPORT}px`);
    expect(view.container.querySelector('[data-mssql-wait-rows]')?.getAttribute('data-mssql-wait-rows')).toBe('5');
    await waitFor(() => {
      expect(view.container.querySelectorAll('[data-mssql-wait-row]')).toHaveLength(8);
    });
    expect(viewport?.getAttribute('style')).toContain('height: 180px');
  });
});
