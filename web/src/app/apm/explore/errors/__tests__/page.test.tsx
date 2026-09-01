import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import ApmErrorsPage from '../page';

const api = {
  getServices: vi.fn(),
  getIssues: vi.fn(),
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
  api.getIssues.mockResolvedValue({ items: [], next_cursor: null, truncated: false });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 错误页信息层级', () => {
  it('空筛选默认查询当前时间窗内全部可见错误', async () => {
    renderWithApmIntl(<ApmErrorsPage />);

    await waitFor(() => expect(api.getIssues).toHaveBeenCalledWith(expect.objectContaining({
      service_name: undefined,
      environment: undefined,
      limit: 50,
    })));
    expect(screen.queryByText('入口归并')).toBeNull();
  });

  it('展示真实异常语义、完整堆栈、分布与 Trace 下钻', async () => {
    api.getIssues.mockResolvedValue({ items: [{
      fingerprint: 'issue-1', exception_type: 'PaymentError', message: 'card declined',
      stacktrace: 'PaymentError\n at charge(payment.py:42)', service_namespace: 'shop', service_name: 'checkout',
      environment: 'prod', occurrences: 2, affected_traces: 2, last_seen_at: '2026-08-06T02:00:00Z',
      version_distribution: [{ value: 'v2', count: 2, percent: 100 }],
      endpoint_distribution: [{ value: 'POST /checkout', count: 2, percent: 100 }],
      sample_traces: [{ trace_id: 'a'.repeat(32), span_id: '1'.repeat(16), endpoint: 'POST /checkout', started_at: '2026-08-06T02:00:00Z', duration_ms: 120 }],
    }], next_cursor: null, truncated: false });

    renderWithApmIntl(<ApmErrorsPage />);

    expect(await screen.findByText('PaymentError')).not.toBeNull();
    expect(screen.getByText('card declined')).not.toBeNull();
    expect(screen.getByText('完整堆栈与分布')).not.toBeNull();
    expect(document.querySelector('details pre')?.textContent).toContain('at charge(payment.py:42)');
    expect(document.querySelector('details pre')?.className).not.toMatch(/bg-/);
    const sampleTrace = screen.getByRole('link', { name: /POST \/checkout/ });
    expect(sampleTrace.getAttribute('href')).toContain('/apm/explore/traces/');
    expect(sampleTrace.className).not.toMatch(/justify-between/);
  });

  it('权限过滤造成当前页为空时仍保留游标入口', async () => {
    api.getIssues.mockResolvedValue({ items: [], next_cursor: 'older-page', truncated: true });

    renderWithApmIntl(<ApmErrorsPage />);

    expect(await screen.findByText('当前游标页没有可见 Issue，可继续加载更早样本。')).not.toBeNull();
    expect(screen.getByRole('button', { name: '加载更多' })).not.toBeNull();
  });
});
