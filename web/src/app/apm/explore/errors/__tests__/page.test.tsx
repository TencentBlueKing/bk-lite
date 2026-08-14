import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmErrorsPage from '../page';

const api = {
  getServices: vi.fn(),
  getTraces: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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
    application_name: '电商应用',
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
  api.getTraces.mockResolvedValue({ items: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 错误页信息层级', () => {
  it('只保留任务所需说明，不重复展示能力规划与遥测依赖文案', async () => {
    renderWithApmIntl(<ApmErrorsPage />);

    await waitFor(() => expect(api.getTraces).toHaveBeenCalled());
    expect(screen.queryByText(/当前版本按错误调用链展示/)).toBeNull();
    expect(screen.queryByText(/以下卡片按入口操作做了客户端归并/)).toBeNull();
    expect(screen.queryByText(/遥测存储不可用/)).toBeNull();
  });

  it('首次进入自动选中可用服务并只查询错误调用链', async () => {
    renderWithApmIntl(<ApmErrorsPage />);

    await waitFor(() => expect(api.getTraces).toHaveBeenCalledWith(expect.objectContaining({
      service_namespace: 'shop',
      service_name: 'checkout',
      environment: 'prod',
      status: 'error',
    })));
  });

  it('默认服务没有错误时自动切换到首个存在错误样本的服务', async () => {
    api.getServices.mockResolvedValue([
      {
        id: 'svc-empty', namespace: 'shop', name: 'catalog',
        environment_views: [{ environment: 'prod' }],
      },
      {
        id: 'svc-error', namespace: 'shop', name: 'checkout',
        environment_views: [{ environment: 'prod' }],
      },
    ]);
    api.getTraces.mockImplementation(async ({ service_name }: { service_name: string }) => ({
      items: service_name === 'checkout' ? [{
        trace_id: 'trace-error-1',
        root_span_name: 'POST /checkout',
        started_at: '2026-08-06T02:00:00Z',
        span_count: 3,
        service_namespace: 'shop',
        service_name: 'checkout',
      }] : [],
    }));

    renderWithApmIntl(<ApmErrorsPage />);

    expect(await screen.findByText('POST /checkout')).not.toBeNull();
    expect(api.getTraces).toHaveBeenCalledWith(expect.objectContaining({
      service_name: 'catalog',
      status: 'error',
    }));
    expect(api.getTraces).toHaveBeenCalledWith(expect.objectContaining({
      service_name: 'checkout',
      status: 'error',
    }));
  });
});
