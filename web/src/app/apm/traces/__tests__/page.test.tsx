import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmTracesPage from '../page';

const api = {
  getSpans: vi.fn(),
  getTraces: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('entity=traces&service_name=checkout&environment=prod'),
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
  api.getSpans.mockResolvedValue({ items: [], next_cursor: null });
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 调用链探索', () => {
  it('自动检索后展示明细命中与耗时分布', async () => {
    render(<ApmTracesPage />);

    expect((await screen.findAllByText('POST /pay')).length).toBeGreaterThan(0);
    expect(screen.getByText('分面筛选')).not.toBeNull();
    expect(screen.getByText('耗时分布')).not.toBeNull();
    expect(screen.getByText(/traces\/s/)).not.toBeNull();
  });

  it('可切换到聚合视图并按服务汇总', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<ApmTracesPage />);
    await screen.findAllByText('POST /pay');

    await user.click(screen.getByRole('radio', { name: '聚合' }));

    expect(await screen.findByText('聚合分析')).not.toBeNull();
    expect(screen.getByText('按服务')).not.toBeNull();
    await waitFor(() => expect(screen.getAllByText('checkout').length).toBeGreaterThan(0));
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
  });
});
