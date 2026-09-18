import React from 'react';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { getTextContext } from '../service.pilot';
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

const navigation = {
  search: new URLSearchParams(),
  replace: vi.fn(),
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ serviceId: 'svc-1' }),
  useSearchParams: () => navigation.search,
  usePathname: () => '/apm/services/svc-1',
  useRouter: () => ({ replace: navigation.replace }),
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

const TRACE_ID = 'a'.repeat(32);

const joined = () => (getTextContext().sections || []).map((section) => section.content).join('\n');

beforeEach(() => {
  navigation.search = new URLSearchParams();
  navigation.replace.mockReset();
  window.history.replaceState({}, '', '/apm/services/svc-1');
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
    request_rate: 4.2,
    error_rate: 0.08,
    p95_ms: 210,
    p99_ms: 380,
    timeseries: [],
    top_endpoints: [{
      endpoint: 'POST /pay',
      request_rate: 4.2,
      error_rate: 0.08,
      p95_ms: 210,
      p99_ms: 380,
    }],
  });
  api.getTraces.mockResolvedValue({
    items: [{
      trace_id: TRACE_ID,
      started_at: '2026-08-24T00:50:00Z',
      duration_ms: 80,
      service_namespace: 'shop',
      service_name: 'checkout',
      environment: 'production',
      instance_id: 'pod-a',
      status: 'error',
      root_span_name: 'GET /cart',
      span_count: 4,
    }],
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
    other_error_count: 0,
    error_types: [{
      error_type: 'payment_declined',
      message: 'password=hunter2',
      count: 2,
      location: 'downstream',
      last_seen_at: '2026-08-24T00:50:00Z',
      sample_traces: [],
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
    }],
  });
  api.getTopology.mockResolvedValue({ nodes: [], edges: [] });
  api.getSlos.mockResolvedValue([]);
  api.getDeployments.mockResolvedValue({ count: 0, items: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('service.pilot 真实页采集', () => {
  it('概览注入 Top 端点与依赖空文案，不读隐藏 Tab', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);
    expect(await screen.findByText('checkout')).not.toBeNull();
    await waitFor(() => expect(joined()).toContain('POST /pay'));
    await user.click(await screen.findByRole('tab', { name: '调用链' }));
    await waitFor(() => expect(joined()).toContain(TRACE_ID));
    await user.click(await screen.findByRole('tab', { name: '概览' }));
    await waitFor(() => expect(joined()).toContain('POST /pay'));
    const text = joined();
    expect(text).toContain('P99');
    expect(text).toContain('近窗内无上游调用');
    expect(text).toContain('近窗内无向下调用');
    expect(text).toContain('当前 Tab: overview');
    expect(text).not.toContain(TRACE_ID);
    expect(text).not.toContain('尚未接入运行时');
    expect(text).not.toContain('payment_declined');
  }, 15_000);

  it('调用链 Tab 注入近窗样本字段，不含 Top 端点', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);
    expect(await screen.findByText('checkout')).not.toBeNull();
    await user.click(await screen.findByRole('tab', { name: '调用链' }));
    await waitFor(() => expect(joined()).toContain(TRACE_ID));
    const text = joined();
    expect(text).toContain('GET /cart');
    expect(text).toContain('checkout');
    expect(text).toContain('当前 Tab: traces');
    expect(text).not.toContain('POST /pay');
    expect(text).not.toContain('近窗内无上游调用');
  }, 15_000);

  it('错误 Tab 注入类型与失败端点，脱敏 message', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApmServiceDetailPage />);
    expect(await screen.findByText('checkout')).not.toBeNull();
    await user.click(await screen.findByRole('tab', { name: '错误' }));
    expect(await screen.findByText('payment_declined')).not.toBeNull();
    await waitFor(() => expect(joined()).toContain('payment_declined'));
    const text = joined();
    expect(text).toContain('入口请求');
    expect(text).toContain('POST /checkout');
    expect(text).toContain('key=[已省略]');
    expect(text).not.toContain('hunter2');
    expect(text).not.toContain('POST /pay');
    expect(text).not.toContain(TRACE_ID);
    const endpointSection = screen.getByText('失败端点').closest('section');
    await user.click(endpointSection!.querySelector('.font-mono') as HTMLElement);
    expect(within(endpointSection!).getByText('POST /checkout')).not.toBeNull();
    await waitFor(() => expect(joined()).toContain('已按端点过滤'));
  }, 15_000);
});
