import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmTracesPage from '../page';

const api = {
  getServices: vi.fn(),
  getSpans: vi.fn(),
  getTraces: vi.fn(),
  isLoading: false,
};

let search = 'entity=traces&service_name=checkout&environment=prod';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

beforeEach(() => {
  search = 'entity=traces&service_name=checkout&environment=prod';
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
  api.getSpans.mockResolvedValue({ items: [], next_cursor: null });
  api.getServices.mockResolvedValue([{
    id: 'svc-1',
    application_id: 'shop',
    application_name: '电商应用',
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
  api.getTraces.mockResolvedValue({
    items: [
      {
        trace_id: 'trace-1',
        started_at: '2026-08-06T02:00:00Z',
        duration_ms: 120,
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'prod',
        instance_id: 'pod-a',
        status: 'ok',
        root_span_name: 'POST /pay',
        span_count: 8,
      },
      {
        trace_id: 'trace-2',
        started_at: '2026-08-06T02:01:00Z',
        duration_ms: 400,
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'prod',
        instance_id: 'pod-a',
        status: 'error',
        root_span_name: 'POST /pay',
        span_count: 12,
      },
    ],
    next_cursor: null,
  });
});

function spanItem(overrides: Record<string, unknown>) {
  return {
    trace_id: 'trace-1',
    started_at: '2026-08-06T02:00:00Z',
    duration_ms: 20,
    service_namespace: 'shop',
    environment: 'local',
    instance_id: 'pod-a',
    status: 'ok',
    http_method: 'GET',
    http_status_code: '200',
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 调用链探索', () => {
  it('自动检索后展示明细命中与耗时分布', async () => {
    renderWithApmIntl(<ApmTracesPage />);

    expect((await screen.findAllByText('POST /pay')).length).toBeGreaterThan(0);
    const columnHeaders = screen.getAllByRole('columnheader').map((header) => header.textContent);
    expect(columnHeaders.indexOf('Trace ID')).toBeLessThan(columnHeaders.indexOf('入口服务'));
    expect(screen.queryByRole('columnheader', { name: '入口服务 / Trace ID' })).toBeNull();
    expect(screen.getByText('快速筛选')).not.toBeNull();
    expect(screen.getByText('耗时分布')).not.toBeNull();
    expect(screen.getByText(/条调用链\/秒/)).not.toBeNull();
  });

  it('可切换到聚合视图并按服务汇总', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithApmIntl(<ApmTracesPage />);
    await screen.findAllByText('POST /pay');

    await user.click(screen.getByRole('radio', { name: '聚合' }));

    expect(await screen.findByText('聚合分析')).not.toBeNull();
    expect(screen.getByText('按服务')).not.toBeNull();
    await waitFor(() => expect(screen.getAllByText('checkout').length).toBeGreaterThan(0));
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
  });

  it('无深链参数时自动查询当前权限与时间窗内全量结果', async () => {
    search = '';
    renderWithApmIntl(<ApmTracesPage />);

    await waitFor(() => expect(api.getSpans).toHaveBeenCalledWith(expect.objectContaining({
      service_namespace: undefined,
      service_name: undefined,
      environment: undefined,
      limit: 50,
    })));
    expect(screen.getByText('快速筛选')).not.toBeNull();
  });

  it('明细列表分页展示，避免一次铺开全部命中', async () => {
    search = '';
    api.getSpans.mockResolvedValue({
      items: Array.from({ length: 25 }, (_, index) => ({
        trace_id: `trace-${index}`,
        span_id: `span-${index}`,
        started_at: '2026-08-06T02:00:00Z',
        duration_ms: 20 + index,
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'prod',
        instance_id: 'pod-a',
        status: 'ok' as const,
        name: `SPAN ${index}`,
        kind: 'server',
        http_method: 'POST',
        http_status_code: '200',
      })),
      next_cursor: 'cursor-2',
    });

    renderWithApmIntl(<ApmTracesPage />);

    expect(await screen.findByText('SPAN 0')).not.toBeNull();
    expect(screen.getByText('SPAN 19')).not.toBeNull();
    expect(screen.queryByText('SPAN 20')).toBeNull();
    expect(screen.getByText('共 25 条')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull();
  });

  it('点击空的耗时输入框不会立刻查询', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithApmIntl(<ApmTracesPage />);
    await screen.findAllByText('POST /pay');
    const callsAfterReady = api.getTraces.mock.calls.length;

    await user.click(screen.getByPlaceholderText('max'));
    await user.click(screen.getByPlaceholderText('min'));

    expect(api.getTraces.mock.calls.length).toBe(callsAfterReady);
  });

  it('耗时筛选在输入数值并确认后才收窄当前命中', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithApmIntl(<ApmTracesPage />);
    await screen.findAllByText('POST /pay');
    const callsAfterReady = api.getTraces.mock.calls.length;

    const max = screen.getByPlaceholderText('max');
    await user.click(max);
    await user.keyboard('200');
    expect(screen.getByText(/命中 2 条/)).not.toBeNull();

    await user.keyboard('{Enter}');
    expect(await screen.findByText(/命中 1 条/)).not.toBeNull();
    expect(screen.getAllByText('POST /pay')).toHaveLength(1);
    expect(api.getTraces.mock.calls.length).toBe(callsAfterReady);
    expect(api.getTraces).not.toHaveBeenCalledWith(expect.objectContaining({
      max_duration_ms: 200,
    }));
  });

  it('Traces 通过右侧详情进入详情页', async () => {
    renderWithApmIntl(<ApmTracesPage />);

    expect((await screen.findAllByText('POST /pay')).length).toBeGreaterThan(0);
    const detailLinks = screen.getAllByRole('link', { name: '详情' });
    expect(detailLinks).toHaveLength(2);
    expect(detailLinks.map((link) => link.getAttribute('href'))).toEqual([
      '/apm/explore/traces/trace-1',
      '/apm/explore/traces/trace-2',
    ]);
  });

  it('Spans 明细行不可点击进入详情', async () => {
    search = '';
    api.getSpans.mockResolvedValue({
      items: [spanItem({ span_id: 's1', service_name: 'checkout', name: 'GET /products', kind: 'server' })],
      next_cursor: null,
    });
    renderWithApmIntl(<ApmTracesPage />);

    expect(await screen.findByText('GET /products')).not.toBeNull();
    expect(screen.queryByRole('button', { name: '详情' })).toBeNull();
    expect(screen.queryByRole('link', { name: '详情' })).toBeNull();
    expect(screen.queryByRole('link', { name: /查看 Span/ })).toBeNull();
  });

  it('快速筛选按当前命中收窄，不会重新填满查询窗口', async () => {
    search = '';
    api.getSpans.mockResolvedValue({
      items: [
        spanItem({ span_id: 's1', service_name: 'demo-storefront', name: 'GET /products', kind: 'server' }),
        spanItem({ span_id: 's2', service_name: 'demo-storefront', name: 'GET /products', kind: 'SERVER' }),
        spanItem({ span_id: 's3', service_name: 'demo-storefront', name: 'GET /products', kind: 'server' }),
        spanItem({ span_id: 's4', service_name: 'demo-catalog', name: 'GET /stock', kind: 'client' }),
        spanItem({ span_id: 's5', service_name: 'demo-catalog', name: 'GET /stock', kind: 'client' }),
        spanItem({ span_id: 's6', service_name: 'demo-inventory', name: 'SELECT featured', kind: 'internal', status: 'error' }),
      ],
      next_cursor: null,
    });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithApmIntl(<ApmTracesPage />);

    expect(await screen.findByText(/命中 6 条/)).not.toBeNull();
    const callsAfterReady = api.getSpans.mock.calls.length;

    await user.click(screen.getByRole('checkbox', { name: /client/i }));
    expect(await screen.findByText(/命中 2 条/)).not.toBeNull();
    expect(screen.getAllByText('GET /stock')).toHaveLength(2);
    expect(screen.queryByText('GET /products')).toBeNull();
    expect(api.getSpans.mock.calls.length).toBe(callsAfterReady);

    await user.click(screen.getByRole('checkbox', { name: /client/i }));
    expect(await screen.findByText(/命中 6 条/)).not.toBeNull();

    await user.click(screen.getByRole('button', { name: /demo-storefront/ }));
    expect(await screen.findByText(/命中 3 条/)).not.toBeNull();
    expect(screen.queryByText('GET /stock')).toBeNull();
    expect(api.getSpans.mock.calls.length).toBe(callsAfterReady);
  });
});
