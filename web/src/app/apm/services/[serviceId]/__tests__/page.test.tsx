import React from 'react';
import { cleanup, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmServiceDetailPage from '../page';

const api = {
  getService: vi.fn(),
  getServiceRed: vi.fn(),
  getServiceErrorBreakdown: vi.fn(),
  getTraces: vi.fn(),
  getTopology: vi.fn(),
  getSlos: vi.fn(),
  getDeployments: vi.fn(),
  setServiceArchived: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ serviceId: 'svc-1' }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/components/time-series-composed-chart', () => ({
  default: () => <div>chart</div>,
}));
vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getService.mockResolvedValue({
    id: 'svc-1',
    application_id: 'shop',
    application_name: 'Shop',
    namespace: 'shop',
    name: 'checkout',
    language: 'python',
    first_seen_at: '2026-08-01T00:00:00Z',
    last_seen_at: '2026-08-24T00:00:00Z',
    archived_at: null,
    archive_reason: '',
    status: 'active',
    environment_views: [{ environment: 'production', last_seen_at: '2026-08-24T00:00:00Z', status: 'active' }],
    organization_ids: [10],
  });
  api.getServiceRed.mockResolvedValue({
    service_id: 'svc-1',
    environment: 'production',
    started_at: '2026-08-24T00:00:00Z',
    ended_at: '2026-08-24T01:00:00Z',
    request_rate: 1,
    error_rate: 0,
    p95_ms: 100,
    p99_ms: 120,
    timeseries: [],
    top_endpoints: [],
  });
  api.getTraces.mockResolvedValue({ items: [] });
  api.getServiceErrorBreakdown.mockResolvedValue({
    service_id: 'svc-1',
    environment: 'production',
    started_at: '2026-08-24T00:00:00Z',
    ended_at: '2026-08-24T01:00:00Z',
    data_state: 'available',
    request_count: 0,
    error_count: 0,
    error_rate: 0,
    failed_endpoints: [],
    other_error_count: 0,
    error_types: [],
    recent_failures: [],
  });
  api.getTopology.mockResolvedValue({ nodes: [], edges: [] });
  api.getSlos.mockResolvedValue([]);
  api.getDeployments.mockResolvedValue({
    count: 1,
    items: [
      {
        id: 'dep-1',
        service_id: 'svc-1',
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'production',
        version: '1.2.0',
        deployed_at: new Date().toISOString(),
        deployed_by: '',
        status: 'success',
        source: 'inferred',
      },
    ],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 服务详情页头', () => {
  it('用面包屑「服务」回到服务目录，而不是依赖已选中的二级菜单', async () => {
    renderWithApmIntl(<ApmServiceDetailPage />);

    const catalogLink = await screen.findByRole('link', { name: '返回服务目录' });
    expect(catalogLink.getAttribute('href')).toBe('/apm/services?perspective=service');
    expect(catalogLink.textContent).toBe('服务');
    expect(screen.getByRole('navigation', { name: '页面路径' })).not.toBeNull();
  }, 15_000);
});

describe('APM 服务详情部署 Tab', () => {
  it('进入部署 Tab 后展示推断部署事件而不是占位文案', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);

    expect(await screen.findByText('checkout')).not.toBeNull();
    expect(api.getDeployments).not.toHaveBeenCalled();

    await user.click(screen.getByRole('tab', { name: '部署' }));

    expect(await screen.findByText('1.2.0')).not.toBeNull();
    expect(screen.getByText('由遥测推断的发布记录')).not.toBeNull();
    expect(screen.getByText('推断')).not.toBeNull();
    expect(screen.queryByText('部署事件将在发布埋点接入后展示；当前可先通过版本与 Trace 属性排查变更。')).toBeNull();
    expect(api.getDeployments).toHaveBeenCalledWith(expect.objectContaining({ service_id: 'svc-1' }));
  }, 15_000);
});

describe('APM 服务详情错误 Tab', () => {
  it('用错误构成接口展示失败端点和错误原因，不再拉 Issue', async () => {
    api.getServiceRed.mockResolvedValue({
      service_id: 'svc-1',
      environment: 'production',
      started_at: '2026-08-24T00:00:00Z',
      ended_at: '2026-08-24T01:00:00Z',
      request_rate: 0.1,
      error_rate: 0.4,
      p95_ms: 1290,
      p99_ms: 3590,
      request_count: 10,
      error_count: 4,
      timeseries: [{ timestamp: '2026-08-24T00:30:00Z', request_rate: 0.1, error_rate: 0.4, p95_ms: 100, p99_ms: 200 }],
      top_endpoints: [],
    });
    api.getServiceErrorBreakdown.mockResolvedValue({
      service_id: 'svc-1',
      environment: 'production',
      started_at: '2026-08-24T00:00:00Z',
      ended_at: '2026-08-24T01:00:00Z',
      data_state: 'available',
      request_count: 10,
      error_count: 4,
      error_rate: 0.4,
      failed_endpoints: [
        { endpoint: 'POST /checkout', error_count: 3, request_count: 8, error_rate: 0.375 },
      ],
      other_error_count: 1,
      error_types: [{
        error_type: 'payment_declined',
        message: '',
        count: 2,
        location: 'downstream',
        last_seen_at: '2026-08-24T00:50:00Z',
        sample_traces: [{
          trace_id: 'a'.repeat(32),
          span_id: '1'.repeat(16),
          endpoint: 'POST /orders',
          started_at: '2026-08-24T00:50:00Z',
        }],
      }],
      recent_failures: [{
        trace_id: 'b'.repeat(32),
        span_id: '2'.repeat(16),
        started_at: '2026-08-24T00:50:00Z',
        duration_ms: 80,
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'production',
        instance_id: 'pod-a',
        status: 'error',
        name: 'POST /checkout',
        kind: 'server',
        http_method: 'POST',
        http_status_code: '502',
      }, {
        trace_id: 'c'.repeat(32),
        span_id: '3'.repeat(16),
        started_at: '2026-08-24T00:49:00Z',
        duration_ms: 40,
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'production',
        instance_id: 'pod-a',
        status: 'error',
        name: 'GET /products',
        kind: 'server',
        http_method: 'GET',
        http_status_code: '500',
      }],
    });
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);

    expect(await screen.findByText('checkout')).not.toBeNull();
    expect(api.getServiceErrorBreakdown).not.toHaveBeenCalled();

    await user.click(screen.getByRole('tab', { name: '错误' }));

    expect(await screen.findByText('payment_declined')).not.toBeNull();
    expect(screen.getAllByText('POST /checkout').length).toBeGreaterThan(0);
    expect(screen.getByText((content) => content.includes('次入口请求') && content.includes('次失败'))).not.toBeNull();
    expect(screen.getByText('失败端点')).not.toBeNull();
    expect(screen.getByText('错误原因')).not.toBeNull();
    expect(screen.getByText(/按错误类型统计/)).not.toBeNull();
    expect(screen.getByText('调下游')).not.toBeNull();
    expect(screen.queryByText(/占失败样本/)).toBeNull();
    expect(screen.queryByText('SpanError')).toBeNull();
    expect(screen.getByRole('link', { name: /POST \/orders/ }).getAttribute('href')).toBe(`/apm/explore/traces/${'a'.repeat(32)}`);
    expect(screen.getByRole('link', { name: '在错误分析中打开' }).getAttribute('href')).toContain('/apm/explore/errors');
    expect(api.getServiceErrorBreakdown).toHaveBeenCalledWith('svc-1', expect.objectContaining({
      environment: 'production',
      sample_limit: 20,
      started_at: api.getServiceRed.mock.calls[0][2],
      ended_at: api.getServiceRed.mock.calls[0][3],
    }));

    const endpointSection = screen.getByText('失败端点').closest('section');
    const recentSection = screen.getByText(/最近 \d+ 条/).closest('section');
    expect(endpointSection).not.toBeNull();
    expect(recentSection).not.toBeNull();
    expect(within(recentSection!).getByText('GET /products')).not.toBeNull();
    await user.click(endpointSection!.querySelector('.font-mono') as HTMLElement);
    expect(screen.getByText('清除端点筛选')).not.toBeNull();
    expect(within(recentSection!).queryByText('GET /products')).toBeNull();
    expect(within(recentSection!).getByText('POST /checkout')).not.toBeNull();
  }, 15_000);

  it('没有失败请求时只显示空态，不展示三个列表区块', async () => {
    api.getServiceErrorBreakdown.mockResolvedValue({
      service_id: 'svc-1',
      environment: 'production',
      started_at: '2026-08-24T00:00:00Z',
      ended_at: '2026-08-24T01:00:00Z',
      data_state: 'available',
      request_count: 10,
      error_count: 0,
      error_rate: 0,
      failed_endpoints: [],
      other_error_count: 0,
      error_types: [],
      recent_failures: [],
    });
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);
    await user.click(await screen.findByRole('tab', { name: '错误' }));

    expect(await screen.findByText('本窗无失败请求')).not.toBeNull();
    expect(screen.queryByText('失败端点')).toBeNull();
    expect(screen.queryByText('错误原因')).toBeNull();
  }, 15_000);
});
