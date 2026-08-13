import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmEndpointsPage from '../page';

const tableMessages = {
  'common.total': '共',
  'common.items': '条',
  'common.checked': '已选',
  'common.confirm': '确认',
  'common.cancel': '取消',
  'common.searchPlaceHolder': '搜索字段',
  'common.selectAll': '全选',
  'common.selected': '已选',
  'common.clear': '清空',
  'common.pin': '固定',
  'common.unpin': '取消固定',
  'cutomTable.fieldSetting': '字段设置',
  'cutomTable.pinHint': '固定字段会显示在表格左侧',
};

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
    render(
      <IntlProvider locale="zh" messages={tableMessages}>
        <ApmEndpointsPage />
      </IntlProvider>,
    );

    expect(await screen.findByText('/pay')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '查看' }));


    expect(await screen.findByText('端点趋势')).not.toBeNull();
    expect(screen.getByTestId('endpoint-trend')).not.toBeNull();
    expect(await screen.findByText('样本调用链')).not.toBeNull();
    await waitFor(() => expect(api.getTraces).toHaveBeenCalled());
    expect(await screen.findByText(/trace-endpoint-1/)).not.toBeNull();
  });

  it('把服务筛选放在左侧，并由表头承载三个指标排序', async () => {
    render(
      <IntlProvider locale="zh" messages={tableMessages}>
        <ApmEndpointsPage />
      </IntlProvider>,
    );

    await screen.findByText('/pay');
    expect(screen.getByRole('combobox', { name: '服务' })).not.toBeNull();
    expect(screen.queryByRole('combobox', { name: '排序' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: /吞吐量/ }).querySelector('.ant-table-column-sorters')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /错误率/ }).querySelector('.ant-table-column-sorters')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: /P95/ }).querySelector('.ant-table-column-sorters')).not.toBeNull();
  });

  it('按容器比例平衡主信息列与指标列', async () => {
    render(
      <IntlProvider locale="zh" messages={tableMessages}>
        <ApmEndpointsPage />
      </IntlProvider>,
    );

    await screen.findByText('/pay');
    const columnWidths = Array.from(document.querySelectorAll('.ant-table colgroup col'))
      .map((column) => (column as HTMLElement).style.width);

    expect(columnWidths).toEqual(['29%', '22%', '14%', '11%', '10%', '9%', '5%']);
    expect(columnWidths.every((width) => width.endsWith('%'))).toBe(true);
    expect(screen.queryByRole('columnheader', { name: '方法' })).toBeNull();
    expect(getComputedStyle(screen.getByRole('columnheader', { name: /吞吐量/ })).textAlign).toBe('right');
    expect(getComputedStyle(screen.getByRole('columnheader', { name: '操作' })).textAlign).toBe('right');
  });
});
