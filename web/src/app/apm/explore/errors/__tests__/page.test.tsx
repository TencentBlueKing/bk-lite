import React from 'react';
import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import type { ApmIssue, ApmIssuePage } from '@/app/apm/types';
import ApmErrorsPage from '../page';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function issue(fingerprint: string): ApmIssue {
  return {
    fingerprint,
    exception_type: fingerprint,
    message: `${fingerprint} message`,
    stacktrace: '',
    service_namespace: 'shop',
    service_name: 'checkout',
    environment: 'prod',
    occurrences: 1,
    affected_traces: 1,
    last_seen_at: '2026-08-06T02:00:00Z',
    version_distribution: [],
    endpoint_distribution: [],
    sample_traces: [],
  };
}

function issuePage(fingerprints: string[], nextCursor: string | null = null): ApmIssuePage {
  return { items: fingerprints.map(issue), next_cursor: nextCursor, truncated: Boolean(nextCursor) };
}

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
    expect(screen.getByText('已加载 1 类错误')).not.toBeNull();
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

describe('APM 错误页过时筛选与分页', () => {
  async function chooseOption(comboboxIndex: number, optionText: string) {
    fireEvent.mouseDown(screen.getAllByRole('combobox')[comboboxIndex]);
    fireEvent.click(await screen.findByText(optionText, { selector: '.ant-select-item-option-content' }));
  }

  it('旧首屏后到时不得覆盖新筛选结果', async () => {
    const stale = deferred<ApmIssuePage>();
    const fresh = deferred<ApmIssuePage>();
    api.getIssues.mockImplementation((params: { service_name?: string }) => (
      params.service_name === 'checkout' ? fresh.promise : stale.promise
    ));

    renderWithApmIntl(<ApmErrorsPage />);
    await waitFor(() => expect(api.getIssues).toHaveBeenCalled());
    await waitFor(() => expect(api.getServices).toHaveBeenCalled());
    await chooseOption(0, 'shop / checkout');
    await waitFor(() => expect(api.getIssues).toHaveBeenCalledWith(expect.objectContaining({
      service_name: 'checkout',
    })));

    await act(async () => {
      fresh.resolve(issuePage(['fresh-fingerprint']));
    });
    expect(await screen.findByText('fresh-fingerprint')).not.toBeNull();

    await act(async () => {
      stale.resolve(issuePage(['stale-fingerprint']));
    });
    await waitFor(() => expect(screen.queryByText('stale-fingerprint')).toBeNull());
    expect(screen.getByText('fresh-fingerprint')).not.toBeNull();
  });

  it('旧分页后到时不得追加到新筛选列表', async () => {
    const more = deferred<ApmIssuePage>();
    const nextFirstPage = deferred<ApmIssuePage>();
    let switched = false;
    api.getIssues.mockImplementation((params: { cursor?: string }) => {
      if (params.cursor === 'older-page') return more.promise;
      if (switched) return nextFirstPage.promise;
      return Promise.resolve(issuePage(['first-fingerprint'], 'older-page'));
    });

    renderWithApmIntl(<ApmErrorsPage />);
    expect(await screen.findByText('first-fingerprint')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }));
    await waitFor(() => expect(api.getIssues).toHaveBeenCalledWith(expect.objectContaining({ cursor: 'older-page' })));

    switched = true;
    await chooseOption(2, '4h');
    await waitFor(() => expect(api.getIssues).toHaveBeenCalledWith(expect.not.objectContaining({ cursor: expect.anything() })));

    await act(async () => {
      nextFirstPage.resolve(issuePage(['filtered-fingerprint']));
    });
    expect(await screen.findByText('filtered-fingerprint')).not.toBeNull();

    await act(async () => {
      more.resolve(issuePage(['stale-page-fingerprint']));
    });
    await waitFor(() => expect(screen.queryByText('stale-page-fingerprint')).toBeNull());
    expect(screen.queryByText('first-fingerprint')).toBeNull();
    expect(screen.getByText('filtered-fingerprint')).not.toBeNull();
  });

  it('同一 cursor 两次 in-flight 只追加一页', async () => {
    const more = deferred<ApmIssuePage>();
    api.getIssues.mockImplementation((params: { cursor?: string }) => {
      if (params.cursor) return more.promise;
      return Promise.resolve(issuePage(['first-fingerprint'], 'older-page'));
    });

    renderWithApmIntl(<ApmErrorsPage />);
    expect(await screen.findByText('first-fingerprint')).not.toBeNull();
    await act(async () => {
      const loadMore = screen.getByRole('button', { name: '加载更多' });
      loadMore.click();
      loadMore.click();
    });

    await act(async () => {
      more.resolve(issuePage(['second-fingerprint']));
    });
    expect(await screen.findByText('second-fingerprint')).not.toBeNull();
    expect(screen.getAllByText('second-fingerprint')).toHaveLength(1);
    expect(screen.getByText('已加载 2 类错误')).not.toBeNull();
  });
});
