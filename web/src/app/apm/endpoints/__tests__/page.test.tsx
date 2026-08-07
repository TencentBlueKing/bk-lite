import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmEndpointsPage from '../page';

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
  it('点击端点行打开详情并加载样本调用链', async () => {
    const user = userEvent.setup();
    render(<ApmEndpointsPage />);

    expect(await screen.findByText('POST /pay')).not.toBeNull();
    await user.click(screen.getByText('POST /pay'));

    expect(await screen.findByText('样本调用链')).not.toBeNull();
    await waitFor(() => expect(api.getTraces).toHaveBeenCalled());
    expect(await screen.findByText(/trace-endpoint-1/)).not.toBeNull();
  });
});
