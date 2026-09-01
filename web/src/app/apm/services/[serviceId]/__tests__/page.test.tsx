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
