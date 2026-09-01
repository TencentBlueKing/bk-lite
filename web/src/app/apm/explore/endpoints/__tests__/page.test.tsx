import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmEndpointsPage from '../page';

const api = {
  getServices: vi.fn(),
  getServiceRed: vi.fn(),
  getTraces: vi.fn(),
  isLoading: false,
};

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/time-series-composed-chart', () => ({
  default: ({ series }: { series: Array<{ name: string }> }) => (
    <div data-testid="endpoint-trend">{series.map((item) => item.name).join(' / ')}</div>
  ),
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getServices.mockResolvedValue([{
    id: 'svc-1',
    application_id: 'shop',
    application_name: 'shop',
    namespace: 'shop',
    name: 'checkout',
    first_seen_at: '2026-08-05T00:00:00Z',
    last_seen_at: '2026-08-06T02:00:00Z',
    archived_at: null,
    archive_reason: '',
    status: 'active',
    environment_views: [{ environment: 'prod', last_seen_at: '2026-08-06T02:00:00Z', status: 'active' }],
    organization_ids: [1],
  }]);
  api.getServiceRed.mockResolvedValue({
    service_id: 'svc-1',
    environment: 'prod',
    started_at: '2026-08-06T01:00:00Z',
    ended_at: '2026-08-06T02:00:00Z',
    request_rate: 10,
    error_rate: 0.01,
    p95_ms: 100,
    p99_ms: 200,
    timeseries: [],
    top_endpoints: [{
      endpoint: 'POST /pay',
      request_rate: 8.2,
      error_rate: 0.05,
      p95_ms: 180,
      p99_ms: 260,
    }],
  });
  api.getTraces.mockResolvedValue({
    items: [{
      trace_id: 'trace-endpoint-1',
      started_at: '2026-08-06T01:50:00Z',
      duration_ms: 220,
      service_namespace: 'shop',
      service_name: 'checkout',
      environment: 'prod',
      instance_id: null,
      status: 'error',
      root_span_name: 'POST /pay',
      span_count: 9,
    }],
    next_cursor: null,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 端点详情抽屉', () => {
  it('通过显式查看操作打开详情并加载样本调用链', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithApmIntl(<ApmEndpointsPage />);

    expect(await screen.findByText('/pay')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '查看' }));


    expect(await screen.findByText('端点趋势')).not.toBeNull();
    expect((document.querySelector('.ant-drawer-content-wrapper') as HTMLElement | null)?.style.width).toBe('56%');
    expect(screen.getAllByTestId('endpoint-trend')).toHaveLength(3);
    const trendCharts = screen.getByTestId('endpoint-trend-charts');
    expect(trendCharts.className).toContain('flex-wrap');
    expect(trendCharts.className).not.toContain('lg:grid-cols-3');
    expect(Array.from(trendCharts.children).every((cell) => {
      const pane = cell.lastElementChild as HTMLElement | null;
      return cell.className.includes('flex-col') && pane?.className.includes('flex-1') && pane.className.includes('min-h-0');
    })).toBe(true);
    expect(screen.getByText('吞吐量（请求/秒）')).not.toBeNull();
    expect(screen.getByText('错误率 %')).not.toBeNull();
    expect(screen.getByText('P95 / P99')).not.toBeNull();
    expect(await screen.findByText('样本调用链')).not.toBeNull();
    await waitFor(() => expect(api.getTraces).toHaveBeenCalled());
    expect(await screen.findByText(/trace-endpoint-1/)).not.toBeNull();
  });

  it('把服务筛选放在左侧，并由表头承载三个指标排序', async () => {
    renderWithApmIntl(<ApmEndpointsPage />);

    await screen.findByText('/pay');
    expect(screen.getByRole('combobox', { name: '服务' })).not.toBeNull();
    expect(screen.queryByRole('combobox', { name: '排序' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: /吞吐量/ }).querySelector('.ant-table-column-sorters')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /错误率/ }).querySelector('.ant-table-column-sorters')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /P95/ }).querySelector('.ant-table-column-sorters')).not.toBeNull();
  });

  it('让主信息列自适应剩余空间，并固定指标与操作列宽度', async () => {
    renderWithApmIntl(<ApmEndpointsPage />);

    await screen.findByText('/pay');
    const columnWidths = Array.from(document.querySelectorAll('.ant-table colgroup col'))
      .map((column) => (column as HTMLElement).style.width);

    expect(columnWidths).toEqual(['', '', '120px', '112px', '104px', '112px', '96px']);
    expect(screen.queryByRole('columnheader', { name: '方法' })).toBeNull();
    expect(getComputedStyle(screen.getByRole('columnheader', { name: /吞吐量/ })).textAlign).toBe('left');
    const actionHeader = screen.getByRole('columnheader', { name: '操作' });
    expect(getComputedStyle(actionHeader).textAlign).toBe('left');
    expect(actionHeader.classList.contains('ant-table-cell-fix-right')).toBe(true);
  });
});
