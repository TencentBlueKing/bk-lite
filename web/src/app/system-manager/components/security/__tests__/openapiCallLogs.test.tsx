import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import dayjs from 'dayjs';

import OpenApiCallLogs from '../openapiCallLogs';

const { getOpenApiCallLogs } = vi.hoisted(() => ({
  getOpenApiCallLogs: vi.fn().mockResolvedValue({ items: [], count: 0 }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value }),
}));

vi.mock('@/app/system-manager/api/security', () => ({
  useSecurityApi: () => ({
    getOpenApiCallLogs,
    exportOpenApiCallLogs: vi.fn(),
  }),
}));

vi.mock('@/components/time-selector', () => ({
  default: React.forwardRef(function TimeSelectorMock() {
    return <div>time-selector</div>;
  }),
}));

vi.mock('@/components/custom-table', () => ({
  default: ({
    columns,
    dataSource,
  }: {
    columns: Array<{
      key: string;
      title: React.ReactNode;
      render?: (value: unknown, record: Record<string, unknown>) => React.ReactNode;
    }>;
    dataSource?: Array<Record<string, unknown>>;
  }) => (
    <div>
      {columns.map((column) => (
        <span key={column.key}>{column.title}</span>
      ))}
      {dataSource?.map((record, index) => (
        <div key={String(record.id ?? index)}>
          {columns.find((column) => column.key === 'detail')?.render?.(undefined, record)}
        </div>
      ))}
    </div>
  ),
}));

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  getOpenApiCallLogs.mockClear();
});

describe('OpenApiCallLogs', () => {
  it('shows primary filters and scan columns only', async () => {
    render(<OpenApiCallLogs />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('system.security.callAccount')).toBeTruthy();
    });
    expect(screen.getByPlaceholderText('system.security.apiCallRequest')).toBeTruthy();
    expect(screen.getByPlaceholderText('system.security.secretName')).toBeTruthy();
    expect(screen.getByPlaceholderText('system.security.sourceIp')).toBeTruthy();
    expect(screen.getByPlaceholderText('system.security.httpStatus')).toBeTruthy();
    expect(screen.getAllByText('system.security.tokenKind').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('system.security.apiKind').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('system.security.apiCallResult').length).toBeGreaterThanOrEqual(1);
    const headers = screen.getByText('system.security.apiCallRequest').parentElement?.textContent || '';
    expect(headers).toContain('system.security.httpStatus');
    expect(headers).toContain('system.security.sourceIp');
    expect(headers).not.toContain('system.security.teamName');
    expect(headers).not.toContain('system.security.secretName');
    expect(headers).not.toContain('system.security.tokenKind');
    expect(headers).not.toContain('system.security.apiKind');
    const userAt = headers.indexOf('system.security.callAccount');
    const requestAt = headers.lastIndexOf('system.security.apiCallRequest');
    expect(userAt).toBeGreaterThanOrEqual(0);
    expect(requestAt).toBeGreaterThan(userAt);
    expect(headers).toContain('system.security.errorCode');
    expect(headers.endsWith('common.actions')).toBe(true);
    expect(headers.indexOf('system.security.apiCallResult')).toBeLessThan(
      headers.lastIndexOf('system.security.errorCode')
    );
  });

  it('opens the detail drawer from the row button without a retrieve call', async () => {
    getOpenApiCallLogs.mockResolvedValueOnce({
      items: [{
        id: 7,
        path: '/openapi/v1/system-mgmt/users',
        method: 'GET',
        call_result: 'success',
        http_status: 200,
        username: 'admin',
      }],
      count: 1,
    });
    render(<OpenApiCallLogs />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'common.detail' })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: 'common.detail' }));
    expect(screen.getByText('system.security.apiCallDetailInfo')).toBeTruthy();
    expect(screen.getByText('/openapi/v1/system-mgmt/users')).toBeTruthy();
  });

  it('reset refetches through the current moment with filters cleared', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-22T08:00:00Z'));
    render(<OpenApiCallLogs />);

    await waitFor(() => {
      expect(getOpenApiCallLogs).toHaveBeenCalled();
    });
    const openedAt = getOpenApiCallLogs.mock.calls[0][0].created_at_end;

    vi.setSystemTime(new Date('2026-09-22T09:00:00Z'));
    fireEvent.change(screen.getByPlaceholderText('system.security.callAccount'), {
      target: { value: 'alice' },
    });
    fireEvent.click(screen.getByRole('button', { name: /common\.reset/ }));

    await waitFor(() => {
      expect(getOpenApiCallLogs.mock.calls.length).toBeGreaterThan(1);
    });
    const resetParams = getOpenApiCallLogs.mock.calls.at(-1)?.[0];
    expect(resetParams.username).toBeUndefined();
    expect(resetParams.created_at_end).toBe(dayjs().format('YYYY-MM-DD HH:mm:ss'));
    expect(resetParams.created_at_end).not.toBe(openedAt);
  });
});
