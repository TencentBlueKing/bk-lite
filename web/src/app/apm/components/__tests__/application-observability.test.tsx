import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApplicationObservability from '../application-observability';

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
vi.mock('@/app/apm/components/organization-assignment-modal', () => ({ default: () => null }));
vi.mock('@/app/apm/services/topology/topology-canvas', () => ({
  default: ({
    nodes,
    edges,
    focusNamespace,
  }: {
    nodes: Array<{ id: string }>;
    edges: Array<{ source: string; target: string }>;
    focusNamespace?: string;
  }) => (
    <div
      data-testid="application-topology"
      data-nodes={nodes.map((node) => node.id).join(',')}
      data-edges={edges.map((edge) => `${edge.source}>${edge.target}`).join(',')}
      data-focus={focusNamespace ?? ''}
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
    ],
    edges: [
      { source: 'shop-node', target: 'billing-node', health: 'healthy', sampled_calls: 1, error_calls: 0, average_duration_ms: 5 },
      { source: 'shop-node', target: 'inferred:prod:mysql', health: 'healthy', sampled_calls: 1, error_calls: 0, average_duration_ms: 4 },
    ],
    sampled_traces: 2, truncated: false, data_state: 'available',
  });
  api.getServiceRed.mockResolvedValue({ request_rate: 3, error_rate: 0.1, p95_ms: 25, p99_ms: 40, data_state: 'available', timeseries: [], top_endpoints: [] });
  api.getEvents.mockResolvedValue([]);
  api.getSlos.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 应用观测详情', () => {
  it('拓扑展示本应用及一跳上下游，关键信息含服务数/告警数/SLO，服务列表与目录一致', async () => {
    renderWithApmIntl(
      <ApplicationObservability applicationId="app-row-1" />,
    );

    expect(await screen.findByText('应用服务拓扑')).not.toBeNull();
    expect(screen.queryByRole('link', { name: '返回服务' })).toBeNull();
    expect(screen.getByRole('radiogroup', { name: '服务指标时间窗口' })).not.toBeNull();
    expect(screen.getByRole('radiogroup', { name: '拓扑布局' })).not.toBeNull();
    expect(screen.getByRole('radio', { name: '层次' })).not.toBeNull();
    expect(screen.getByRole('radio', { name: '力导向' })).not.toBeNull();
    expect(screen.getByText('关键信息')).not.toBeNull();
    expect(screen.getByText('服务数')).not.toBeNull();
    expect(screen.getByText('告警数')).not.toBeNull();
    expect(screen.getAllByText('SLO').length).toBeGreaterThan(0);
    expect(screen.queryByText('应用 KPI')).toBeNull();

    const topology = await screen.findByTestId('application-topology');
    await waitFor(() => {
      expect(topology.getAttribute('data-nodes')?.split(',').sort()).toEqual(['billing-node', 'inferred:prod:mysql', 'shop-node']);
      expect(topology.getAttribute('data-edges')?.split(',').sort()).toEqual(['shop-node>billing-node', 'shop-node>inferred:prod:mysql']);
      expect(topology.getAttribute('data-focus')).toBe('shop');
    });
    expect(api.getTopology).toHaveBeenCalledWith(expect.objectContaining({
      include_inferred: true,
      include_user_request: true,
    }));

    expect(await screen.findByText('checkout')).not.toBeNull();
    expect(screen.queryByText('invoice')).toBeNull();
    expect(screen.queryByRole('link', { name: 'mysql' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: /服务/ })).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: '活跃告警' })).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: '吞吐量（请求/秒）' })).not.toBeNull();
    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalled());
  });

  it('拓扑取数完成前展示加载而不是空状态', async () => {
    let resolveTopology: (value: unknown) => void = () => undefined;
    api.getTopology.mockImplementation(() => new Promise((resolve) => {
      resolveTopology = resolve;
    }));

    renderWithApmIntl(<ApplicationObservability applicationId="app-row-1" />);

    expect(await screen.findByText('应用服务拓扑')).not.toBeNull();
    expect(screen.getByLabelText('加载 APM 数据')).not.toBeNull();
    expect(screen.queryByText('当前时间窗暂无应用内调用关系。')).toBeNull();
    expect(screen.queryByTestId('application-topology')).toBeNull();

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
});
