import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmServiceDetailPage from '../page';

const api = {
  getService: vi.fn(),
  getServiceRed: vi.fn(),
  getTraces: vi.fn(),
  getIssues: vi.fn(),
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
  api.getIssues.mockResolvedValue({ items: [], next_cursor: null, truncated: false });
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
  it('按入口 ERROR Span 拉 Issue，不依赖最近调用链是否抽到错误', async () => {
    api.getServiceRed.mockResolvedValue({
      service_id: 'svc-1',
      environment: 'production',
      started_at: '2026-08-24T00:00:00Z',
      ended_at: '2026-08-24T01:00:00Z',
      request_rate: 0.1,
      error_rate: 0.0279,
      p95_ms: 1290,
      p99_ms: 3590,
      request_count: 3588,
      error_count: 100,
      timeseries: [],
      top_endpoints: [],
    });
    api.getTraces.mockResolvedValue({
      items: [{
        trace_id: 'ok-trace',
        started_at: '2026-08-24T00:50:00Z',
        duration_ms: 80,
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'production',
        instance_id: 'pod-a',
        status: 'ok',
        root_span_name: 'POST /checkout',
        span_count: 3,
      }],
    });
    api.getIssues.mockResolvedValue({
      items: [{
        fingerprint: 'issue-1',
        exception_type: 'PaymentError',
        message: 'card declined',
        stacktrace: 'PaymentError\n at charge(payment.py:42)',
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'production',
        occurrences: 10,
        affected_traces: 10,
        last_seen_at: '2026-08-24T00:50:00Z',
        version_distribution: [{ value: 'v2', count: 10, percent: 100 }],
        endpoint_distribution: [{ value: 'POST /checkout', count: 10, percent: 100 }],
        sample_traces: [{
          trace_id: 'a'.repeat(32),
          span_id: '1'.repeat(16),
          endpoint: 'POST /checkout',
          started_at: '2026-08-24T00:50:00Z',
          duration_ms: 120,
        }],
      }],
      next_cursor: 'older-page',
      truncated: true,
    });
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);

    expect(await screen.findByText('checkout')).not.toBeNull();
    expect(api.getIssues).not.toHaveBeenCalled();

    await user.click(screen.getByRole('tab', { name: '错误' }));

    expect(await screen.findByText('PaymentError')).not.toBeNull();
    expect(screen.getByText('card declined')).not.toBeNull();
    expect(screen.getByText((content) => content.includes('次入口请求') && content.includes('次失败'))).not.toBeNull();
    expect(screen.getByText(/占失败样本/)).not.toBeNull();
    expect(screen.queryByRole('tab', { name: '错误 (1)' })).toBeNull();
    expect(screen.getByRole('tab', { name: '错误' })).not.toBeNull();
    expect(screen.queryByText('加载更多')).toBeNull();
    expect(screen.getByRole('link', { name: '在错误分析中打开' }).getAttribute('href')).toContain('/apm/explore/errors');
    expect(screen.queryByText('当前时间窗暂无错误 Trace')).toBeNull();
    expect(api.getIssues).toHaveBeenCalledWith(expect.objectContaining({
      service_namespace: 'shop',
      service_name: 'checkout',
      environment: 'production',
      entry_only: true,
      limit: 50,
    }));
  }, 15_000);
});
