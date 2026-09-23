import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
  default: ({ columns }: { columns: Array<{ key: string; title: React.ReactNode }> }) => (
    <div>
      {columns.map((column) => (
        <span key={column.key}>{column.title}</span>
      ))}
    </div>
  ),
}));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  getOpenApiCallLogs.mockClear();
});

describe('OpenApiCallLogs', () => {
  it('shows primary filters and scan columns only', async () => {
    render(<OpenApiCallLogs />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('system.user.table.username')).toBeTruthy();
    });
    expect(screen.getByPlaceholderText('system.security.apiCallRequest')).toBeTruthy();
    expect(screen.getAllByText('system.security.tokenKind').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('system.security.apiKind').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('system.security.apiCallResult').length).toBeGreaterThanOrEqual(1);
    const headers = screen.getByText('system.security.apiCallRequest').parentElement?.textContent || '';
    expect(headers).toContain('system.security.sourceIp');
    const userAt = headers.indexOf('system.user.table.username');
    const teamAt = headers.indexOf('system.security.teamName');
    const kindAt = headers.indexOf('system.security.tokenKind');
    const nameAt = headers.indexOf('system.security.secretName');
    const requestAt = headers.lastIndexOf('system.security.apiCallRequest');
    expect(userAt).toBeGreaterThanOrEqual(0);
    expect(teamAt).toBeGreaterThan(userAt);
    expect(kindAt).toBeGreaterThan(teamAt);
    expect(nameAt).toBeGreaterThan(kindAt);
    expect(requestAt).toBeGreaterThan(nameAt);
    expect(headers.endsWith('system.security.errorCode')).toBe(true);
    expect(headers).not.toContain('common.actions');
    expect(headers.indexOf('system.security.apiCallResult')).toBeLessThan(
      headers.lastIndexOf('system.security.errorCode')
    );
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
    fireEvent.change(screen.getByPlaceholderText('system.user.table.username'), {
      target: { value: 'alice' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'common.reset' }));

    await waitFor(() => {
      expect(getOpenApiCallLogs.mock.calls.length).toBeGreaterThan(1);
    });
    const resetParams = getOpenApiCallLogs.mock.calls.at(-1)?.[0];
    expect(resetParams.username).toBeUndefined();
    expect(resetParams.created_at_end).toBe(dayjs().format('YYYY-MM-DD HH:mm:ss'));
    expect(resetParams.created_at_end).not.toBe(openedAt);
  });
});
