import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApplicationObservability from '../application-observability';
import { HandledRequestError } from '@/utils/request';

const api = {
  getApplication: vi.fn(),
  getServices: vi.fn(),
  getServiceRed: vi.fn(),
  getTopology: vi.fn(),
  getEvents: vi.fn(),
  getSlos: vi.fn(),
  setServiceArchived: vi.fn(),
  setServiceOrganizations: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ applicationId: 'app-row-1' }),
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
  }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ flatGroups: [{ id: 1, name: 'Default' }] }),
}));
vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/app/apm/services/topology/topology-canvas', () => ({
  default: ({
    nodes,
    edges,
    focusNamespace,
    layout,
    fillHeight,
  }: {
    nodes: Array<{ id: string }>;
    edges: Array<{ source: string; target: string }>;
    focusNamespace?: string;
    layout?: string;
    fillHeight?: boolean;
  }) => (
    <div
      data-testid="application-topology"
      data-nodes={nodes.map((node) => node.id).join(',')}
      data-edges={edges.map((edge) => `${edge.source}>${edge.target}`).join(',')}
      data-focus={focusNamespace ?? ''}
      data-layout={layout ?? 'layered'}
      data-fill-height={fillHeight ? 'true' : 'false'}
    />
  ),
}));

const service = (id: string, applicationId: string, name: string) => ({
  id,
  application_id: applicationId,
  application_name: applicationId,
  namespace: applicationId,
  name,
  language: 'python',
  first_seen_at: '2026-08-14T00:00:00Z',
  last_seen_at: '2026-08-14T01:00:00Z',
  archived_at: null,
  archive_reason: '',
  status: 'active' as const,
  environment_views: [{ environment: 'prod', last_seen_at: '2026-08-14T01:00:00Z', status: 'active' as const }],
  organization_ids: [1],
});

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
  api.getApplication.mockResolvedValue({
    id: 'app-row-1', application_id: 'shop', name: '电商应用', description: '订单链路', is_builtin: false,
    service_count: 1, organization_ids: [1], created_at: '2026-08-14T00:00:00Z', updated_at: '2026-08-14T00:00:00Z', created_by: 'admin', updated_by: 'admin',
  });
  api.getServices.mockResolvedValue([service('shop-service', 'shop', 'checkout'), service('billing-service', 'billing', 'invoice')]);
  api.getTopology.mockResolvedValue({
    nodes: [
      { id: 'shop-node', service_namespace: 'shop', service_name: 'checkout', environment: 'prod', health: 'healthy', sampled_spans: 2, error_spans: 0 },
      { id: 'billing-node', service_namespace: 'billing', service_name: 'invoice', environment: 'prod', health: 'healthy', sampled_spans: 1, error_spans: 0 },
      { id: 'inferred:prod:mysql', service_namespace: '', service_name: 'mysql', environment: 'prod', health: 'healthy', sampled_spans: 1, error_spans: 0, kind: 'inferred', fold_key: 'mysql' },
      { id: 'user_request:prod', service_namespace: '', service_name: 'user_request', environment: 'prod', health: 'unknown', sampled_spans: 1, error_spans: 0, kind: 'user_request' },
    ],
    edges: [
      { source: 'shop-node', target: 'billing-node', health: 'healthy', sampled_calls: 1, error_calls: 0, average_duration_ms: 5 },
      { source: 'shop-node', target: 'inferred:prod:mysql', health: 'healthy', sampled_calls: 1, error_calls: 0, average_duration_ms: 4 },
      { source: 'user_request:prod', target: 'shop-node', health: 'unknown', sampled_calls: 1, error_calls: 0, average_duration_ms: 8 },
    ],
    sampled_traces: 2, truncated: false, data_state: 'available',
  });
  api.getServiceRed.mockResolvedValue({
    request_rate: 3,
    error_rate: 0.1,
    p95_ms: 25,
    p99_ms: 40,
    request_count: 1200,
    error_count: 120,
    data_state: 'available',
    timeseries: [
      { timestamp: '2026-08-14T00:00:00Z', request_rate: 2, error_rate: 0.1, p95_ms: 20, p99_ms: 35 },
      { timestamp: '2026-08-14T00:05:00Z', request_rate: 4, error_rate: 0.1, p95_ms: 25, p99_ms: 40 },
    ],
    top_endpoints: [
      { endpoint: 'GET /checkout', request_rate: 2, error_rate: 0.2, p95_ms: 25, p99_ms: 40 },
      { endpoint: 'GET /health', request_rate: 1, error_rate: 0, p95_ms: 2, p99_ms: 3 },
    ],
  });
  api.getEvents.mockResolvedValue([]);
  api.getSlos.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 应用观测详情', () => {
  it('一屏布局：拓扑撑满左侧，关键信息含服务数/告警数/SLO 与 Top 端点，底部一行 KPI 带迷你趋势，不再有服务列表', async () => {
    renderWithApmIntl(
      <ApplicationObservability applicationId="app-row-1" />,
    );

    expect(await screen.findByText('电商应用')).not.toBeNull();
    expect(screen.queryByText('应用服务拓扑')).toBeNull();
    const catalogLink = screen.getByRole('link', { name: '返回应用目录' });
    expect(catalogLink.getAttribute('href')).toBe('/apm/services');
    expect(catalogLink.textContent).toBe('应用');
    expect(screen.getByRole('radiogroup', { name: '服务指标时间窗口' })).not.toBeNull();
    expect(screen.queryByRole('radiogroup', { name: '拓扑布局' })).toBeNull();
    expect(screen.getByText('关键信息')).not.toBeNull();
    expect(screen.getByLabelText('重点指标')).not.toBeNull();
    expect(screen.getByText('接入服务')).not.toBeNull();
    expect(screen.getByText('告警数')).not.toBeNull();
    expect(screen.getAllByText('SLO').length).toBeGreaterThan(0);
    expect(screen.queryByText('应用 KPI')).toBeNull();

    const topology = await screen.findByTestId('application-topology');
    await waitFor(() => {
      expect(topology.getAttribute('data-nodes')?.split(',').sort()).toEqual([
        'billing-node',
        'inferred:prod:mysql',
        'shop-node',
        'user_request:prod',
      ]);
      expect(topology.getAttribute('data-edges')?.split(',').sort()).toEqual([
        'shop-node>billing-node',
        'shop-node>inferred:prod:mysql',
        'user_request:prod>shop-node',
      ]);
      expect(topology.getAttribute('data-focus')).toBe('shop');
      expect(topology.getAttribute('data-layout')).toBe('layered');
      expect(topology.getAttribute('data-fill-height')).toBe('true');
    });
    expect(api.getTopology).toHaveBeenCalledWith(expect.objectContaining({
      include_inferred: true,
      include_user_request: true,
    }));
    expect(api.getTopology.mock.calls[0][0].include_user_request).toBe(true);

    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalledTimes(1));
    expect(api.getServiceRed.mock.calls[0][0]).toBe('shop-service');

    // 底部四卡：吞吐 / 错误率带窗口总量，P95 / P99 带迷你趋势；服务数只计本应用接入服务
    const kpiOf = (key: string) => document.querySelector(`[data-kpi="${key}"]`);
    await waitFor(() => expect(kpiOf('throughput')?.textContent).toContain('3.0/秒'));
    expect(kpiOf('throughput')?.textContent).toContain('1,200 请求');
    expect(kpiOf('throughput')?.getAttribute('data-kpi-trend')).toBe('true');
    expect(kpiOf('error-rate')?.textContent).toContain('10.0%');
    expect(kpiOf('error-rate')?.textContent).toContain('120 错误');
    expect(kpiOf('error-rate')?.getAttribute('data-kpi-trend')).toBe('true');
    expect(kpiOf('p95')?.textContent).toContain('25毫秒');
    expect(kpiOf('p99')?.textContent).toContain('40毫秒');
    expect(kpiOf('p99')?.getAttribute('data-kpi-trend')).toBe('true');
    expect(kpiOf('request-count')).toBeNull();
    expect(kpiOf('error-count')).toBeNull();
    expect(document.querySelectorAll('[data-kpi]').length).toBe(4);
    expect(document.querySelector('[data-key-info="services"]')?.textContent).toMatch(/接入服务\s*1/);

    // 右侧关键信息：Top 端点排行进入侧栏
    expect(screen.getByText('最慢端点')).not.toBeNull();
    expect(screen.getByText('错误端点')).not.toBeNull();
    const slowest = screen.getAllByRole('link', { name: /GET \/checkout/ });
    expect(slowest.length).toBe(2);
    expect(slowest[0].getAttribute('href')).toBe('/apm/explore/endpoints?service=checkout&environment=prod&endpoint=GET+%2Fcheckout');
    expect(screen.getAllByRole('link', { name: /GET \/health/ }).length).toBe(1);

    // 不再展示服务列表表格
    expect(screen.queryByRole('columnheader', { name: '活跃告警' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: '吞吐量（请求/秒）' })).toBeNull();
    expect(screen.queryByText('invoice')).toBeNull();
  }, 15_000);

  it('全部服务 RED 查询失败时重点指标展示错误态并可重试', async () => {
    api.getServiceRed.mockRejectedValue(new Error('boom'));
    renderWithApmIntl(<ApplicationObservability applicationId="app-row-1" />);

    expect(await screen.findByLabelText('重点指标')).not.toBeNull();
    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('1 个服务指标查询失败，重试')).not.toBeNull();
    expect(document.querySelector('[data-kpi]')).toBeNull();
  });

  it('拓扑取数完成前展示加载而不是空状态', async () => {
    let resolveTopology: (value: unknown) => void = () => undefined;
    api.getTopology.mockImplementation(() => new Promise((resolve) => {
      resolveTopology = resolve;
    }));

    renderWithApmIntl(<ApplicationObservability applicationId="app-row-1" />);

    expect(await screen.findByText('电商应用')).not.toBeNull();
    expect(screen.getByLabelText('加载 APM 数据')).not.toBeNull();
    expect(screen.queryByText('当前时间窗暂无应用内调用关系。')).toBeNull();
    expect(screen.queryByTestId('application-topology')).toBeNull();
    // 高负载下 passive effect 可能晚于断言触发，先等拓扑请求真正发出再放行，避免 resolver 尚未挂接。
    await waitFor(() => expect(api.getTopology).toHaveBeenCalled());

    resolveTopology({
      nodes: [
        { id: 'shop-node', service_namespace: 'shop', service_name: 'checkout', environment: 'prod', health: 'healthy', sampled_spans: 2, error_spans: 0 },
      ],
      edges: [],
      sampled_traces: 1,
      truncated: false,
      data_state: 'available',
    });

    await waitFor(() => expect(screen.getByTestId('application-topology')).not.toBeNull());
    expect(screen.queryByText('当前时间窗暂无应用内调用关系。')).toBeNull();
  });

  it('遥测 503 展示不可用而不是暂无调用关系', async () => {
    api.getTopology.mockRejectedValue(new HandledRequestError('VictoriaTraces 查询不可用', {
      status: 503,
      code: 'telemetry_unavailable',
    }));

    renderWithApmIntl(<ApplicationObservability applicationId="app-row-1" />);

    expect(await screen.findByText('电商应用')).not.toBeNull();
    expect(await screen.findByText('遥测存储暂不可用')).not.toBeNull();
    expect(screen.queryByText('当前时间窗暂无应用内调用关系。')).toBeNull();
    expect(screen.queryByTestId('application-topology')).toBeNull();
  });

  it('选择 7d 窗口仍查询 RED 指标', async () => {
    const user = userEvent.setup();
    renderWithApmIntl(<ApplicationObservability applicationId="app-row-1" />);
    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalled());
    api.getServiceRed.mockClear();

    await user.click(screen.getByRole('radio', { name: '7d' }).closest('label')!);

    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalled());
    const startedAt = api.getServiceRed.mock.calls[0][2] as string;
    const endedAt = api.getServiceRed.mock.calls[0][3] as string;
    expect(new Date(endedAt).getTime() - new Date(startedAt).getTime()).toBeGreaterThan(6 * 24 * 60 * 60 * 1000);
    expect(screen.queryByText('RED 指标查询失败')).toBeNull();
  });
});
