import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmApplicationDetailPage from '../page';

const api = {
  getApplication: vi.fn(),
  getServices: vi.fn(),
  getServiceRed: vi.fn(),
  getTopology: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({ useParams: () => ({ applicationId: 'app-row-1' }) }));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));
vi.mock('@/app/apm/services/topology/page', () => ({
  TopologyCanvas: ({ nodes, edges }: { nodes: Array<{ id: string }>; edges: Array<{ source: string; target: string }> }) => (
    <div data-testid="application-topology" data-nodes={nodes.map((node) => node.id).join(',')} data-edges={edges.map((edge) => `${edge.source}>${edge.target}`).join(',')} />
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
    matches: false,
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
    ],
    edges: [{ source: 'shop-node', target: 'billing-node', health: 'healthy', sampled_calls: 1, error_calls: 0, average_duration_ms: 5 }],
    sampled_traces: 2, truncated: false, data_state: 'available',
  });
  api.getServiceRed.mockResolvedValue({ request_rate: 3, error_rate: 0.1, p95_ms: 25, p99_ms: 40, data_state: 'available', timeseries: [], top_endpoints: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 应用详情', () => {
  it('拓扑、KPI 与服务列表都严格限定在当前应用', async () => {
    renderWithApmIntl(<ApmApplicationDetailPage />);

    const topology = await screen.findByTestId('application-topology');
    expect(topology.getAttribute('data-nodes')).toBe('shop-node');
    expect(topology.getAttribute('data-edges')).toBe('');
    expect(await screen.findByText('checkout')).not.toBeNull();
    expect(screen.queryByText('invoice')).toBeNull();
    await waitFor(() => expect(api.getServiceRed).toHaveBeenCalledTimes(1));
  });
});
