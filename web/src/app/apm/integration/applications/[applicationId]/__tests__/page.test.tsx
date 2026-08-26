import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmApplicationDetailPage from '../page';

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
  default: () => <div data-testid="application-topology" />,
}));

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
  api.getServices.mockResolvedValue([]);
  api.getTopology.mockResolvedValue({ nodes: [], edges: [], sampled_traces: 0, truncated: false, data_state: 'no_data' });
  api.getEvents.mockResolvedValue([]);
  api.getSlos.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 集成应用详情入口', () => {
  it('保留添加接入且不展示返回列表', async () => {
    renderWithApmIntl(<ApmApplicationDetailPage />);
    expect(await screen.findByText('应用服务拓扑')).not.toBeNull();
    expect(screen.queryByRole('link', { name: '返回列表' })).toBeNull();
    const addIngest = screen.getAllByRole('link', { name: '添加接入' });
    expect(addIngest.length).toBeGreaterThan(0);
    expect(addIngest.every((link) => link.getAttribute('href') === '/apm/integration/add?application_id=shop')).toBe(true);
  });
});
