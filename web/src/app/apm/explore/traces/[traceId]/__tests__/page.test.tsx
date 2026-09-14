import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import { HandledRequestError } from '@/utils/request';
import ApmTraceDetailPage from '../page';

const api = {
  getTrace: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ traceId: 'trace-1' }),
  useSearchParams: () => new URLSearchParams(),
}));
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
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getTrace.mockResolvedValue({
    trace_id: 'trace-1',
    service_namespace: 'shop',
    service_name: 'checkout',
    environment: 'prod',
    instance_id: 'pod-a',
    truncated: false,
    spans: [
      {
        span_id: 'span-ok',
        parent_span_id: null,
        name: 'GET /ok',
        started_at: '2026-08-06T02:00:00.000Z',
        duration_ms: 40,
        status: 'ok',
        attributes: {},
        service_namespace: 'shop',
        service_name: 'gateway',
        environment: 'prod',
        instance_id: 'pod-a',
        kind: 'server',
      },
      {
        span_id: 'span-error',
        parent_span_id: 'span-ok',
        name: 'POST /pay',
        started_at: '2026-08-06T02:00:00.010Z',
        duration_ms: 180,
        status: 'error',
        attributes: {
          'http.status_code': 500,
          'resource_attr:deployment.environment': 'prod',
        },
        service_namespace: 'shop',
        service_name: 'checkout',
        environment: 'prod',
        instance_id: 'pod-b',
        kind: 'server',
      },
    ],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM Trace 详情', () => {
  it('Trace 超限时展示数据量过大而不是存储不可用', async () => {
    api.getTrace.mockRejectedValue(new HandledRequestError('VictoriaTraces 响应超过大小上限', {
      status: 503,
      code: 'query_too_large',
    }));

    renderWithApmIntl(<ApmTraceDetailPage />);

    expect(await screen.findByText('本次查询数据量过大')).not.toBeNull();
    expect(screen.queryByText('遥测存储暂不可用')).toBeNull();
  });

  it('默认选中首个错误 Span，并支持跳到首个错误', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithApmIntl(<ApmTraceDetailPage />);

    expect(await screen.findByText('服务耗时分解')).not.toBeNull();
    expect(screen.getByText('跳到首个错误')).not.toBeNull();
    expect(screen.getByText('含错误')).not.toBeNull();
    expect(screen.getByText('Trace ID').closest('section')).toBe(screen.getByText('Span 数').closest('section'));
    expect(screen.getByRole('radiogroup', { name: 'Trace 视图模式' }).closest('section')?.textContent).toContain('spans');
    expect((await screen.findAllByText('POST /pay')).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText('http.status_code')).not.toBeNull());

    await user.click(screen.getByRole('radio', { name: '跨度列表' }));
    expect((await screen.findAllByText('POST /pay')).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('radio', { name: '火焰图' }));
    const flameSpan = await screen.findByLabelText('checkout · POST /pay');
    expect(flameSpan.parentElement?.className).not.toContain('min-w-[640px]');
    expect(screen.getByRole('radio', { name: '火焰图' })).not.toBeNull();

    await user.click(screen.getByRole('button', { name: '跳到首个错误' }));
    await waitFor(() => expect(screen.getByText('http.status_code')).not.toBeNull());
    expect(screen.getByText('resource_attr:deployment.environment')).not.toBeNull();

    const attributeTable = screen.getByRole('columnheader', { name: '值' }).closest('.ant-table');
    const columnWidths = Array.from(attributeTable?.querySelectorAll('colgroup col') ?? [])
      .map((column) => (column as HTMLElement).style.width);
    expect(columnWidths).toEqual(['58%', '42%']);
  });
});
