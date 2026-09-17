import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const apis = vi.hoisted(() => ({
  getAlertSnapshots: vi.fn(),
}));

const mockTranslate = (key: string, defaultVal?: string) => defaultVal || key;

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: mockTranslate,
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (time: string) => `formatted-${time}`,
  }),
}));

vi.mock('@/app/log/api/event', () => ({
  default: () => ({
    getAlertSnapshots: async (...args: unknown[]) => apis.getAlertSnapshots(...args),
  }),
}));

import AlertRawLogWidget from '../AlertRawLogWidget';
import { HandledRequestError } from '@/utils/request';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });

  Object.assign(navigator, {
    clipboard: {
      writeText: vi.fn().mockResolvedValue(undefined),
    },
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AlertRawLogWidget Component', () => {
  it('renders loading then empty state when snapshots list is empty', async () => {
    apis.getAlertSnapshots.mockResolvedValueOnce({
      alert_info: { id: 'alert-1', source_id: 'policy-10' },
      snapshots: [],
    });

    render(<AlertRawLogWidget logAlertId="alert-1" />);

    await waitFor(() => {
      expect(screen.getByText('common.noData')).toBeTruthy();
    });
  });

  it('renders error state and handles retry button click', async () => {
    apis.getAlertSnapshots.mockRejectedValueOnce(
      new HandledRequestError('Not found', { status: 404 }),
    );

    render(<AlertRawLogWidget logAlertId="alert-err" />);

    await waitFor(() => {
      expect(screen.getByText('log.event.publicWidgetNotFound')).toBeTruthy();
    });

    apis.getAlertSnapshots.mockResolvedValueOnce({
      snapshots: [
        {
          event_id: 'ev-1',
          snapshot_time: '2026-09-16T10:00:00Z',
          raw_data: [{ _time: '2026-09-16T10:00:00Z', _msg: 'retry worked' }],
          query_clue: { policy_name: 'pol-1', alert_condition: { query: 'err' } },
        },
      ],
    });

    fireEvent.click(screen.getByText('common.retry'));

    await waitFor(() => {
      expect(screen.getByText('retry worked')).toBeTruthy();
    });
  });

  it('defaults to latest snapshot, displays thin header, humanized clues, and tabular log', async () => {
    apis.getAlertSnapshots.mockResolvedValueOnce({
      alert_info: {
        id: 'alert-123',
        source_id: 'policy-auth-fail',
      },
      snapshots: [
        {
          event_id: 'ev-old',
          event_time: '2026-09-16T09:00:00Z',
          query_clue: {
            policy_name: 'Auth Policy Old',
            alert_type: 'keyword',
            collect_type_name: 'file',
            log_groups: ['old-group'],
            period: { type: 'min', value: 10 },
            alert_condition: { query: 'login_fail' },
          },
          raw_data: [{ _time: '2026-09-16T09:00:00Z', _msg: 'old failure' }],
        },
        {
          event_id: 'ev-new',
          event_time: '2026-09-16T10:00:00Z',
          query_clue: {
            policy_name: 'Auth Policy New',
            alert_type: 'keyword',
            collect_type_name: 'container',
            log_groups: ['auth-service', 'k8s-pod'],
            period: { type: 'min', value: 5 },
            window_start: '2026-09-16T09:55:00Z',
            window_end: '2026-09-16T10:00:00Z',
            alert_condition: {
              query: 'failed login',
              rule: {
                mode: 'and',
                conditions: [{ field: 'attempt', op: '>=', value: '3' }],
              },
              group_by: ['user_ip'],
            },
          },
          raw_data: [
            {
              _time: '2026-09-16T10:00:00Z',
              _msg: 'failed login attempt exceeded',
              user_ip: '10.0.0.99',
            },
          ],
        },
      ],
    });

    render(<AlertRawLogWidget logAlertId="alert-123" />);

    // 1. Check thin header
    await waitFor(() => {
      expect(screen.getByText('policy-auth-fail')).toBeTruthy();
      expect(screen.getByText('2')).toBeTruthy(); // snapshot count: 2
    });

    // 2. Default to latest snapshot (ev-new)
    expect(screen.getByText('Auth Policy New')).toBeTruthy();
    expect(screen.getByText('container')).toBeTruthy();
    expect(screen.getByText('auth-service')).toBeTruthy();
    expect(screen.getByText('k8s-pod')).toBeTruthy();
    expect(screen.getByText('failed login')).toBeTruthy();
    expect(screen.getByText('attempt')).toBeTruthy();
    expect(screen.getByText('>=')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
    expect(screen.getByText('user_ip')).toBeTruthy();
    expect(screen.getByText('log.event.queryWindow')).toBeTruthy();
    expect(
      screen.getByText('formatted-2026-09-16T09:55:00Z ~ formatted-2026-09-16T10:00:00Z'),
    ).toBeTruthy();

    // 3. Check table view for raw log
    expect(screen.getByText('failed login attempt exceeded')).toBeTruthy();
    expect(screen.getByText('formatted-2026-09-16T10:00:00Z')).toBeTruthy();

    // 4. Test copy button
    const copyBtn = screen.getByText('common.copy');
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalled();

    // 5. Switch to JSON view using Segmented
    const jsonTab = screen.getByText('log.event.jsonView');
    fireEvent.click(jsonTab);
    await waitFor(() => {
      expect(screen.getByText(/"user_ip": "10\.0\.0\.99"/)).toBeTruthy();
    });

    // 6. Test snapshot switching to historical snapshot (ev-old)
    const combobox = screen.getByRole('combobox');
    fireEvent.mouseDown(combobox);
    // Since Select options use snapshotOptions labels:
    // "#1 · formatted-2026-09-16T09:00:00Z"
    const oldOption = screen.getByTitle(/#1 · formatted-2026-09-16T09:00:00Z/);
    fireEvent.click(oldOption);

    await waitFor(() => {
      expect(screen.getByText('Auth Policy Old')).toBeTruthy();
      expect(screen.getByText('login_fail')).toBeTruthy();
    });

    // Back to latest button appears
    const backBtn = screen.getByText('log.event.backToLatest');
    fireEvent.click(backBtn);
    await waitFor(() => {
      expect(screen.getByText('Auth Policy New')).toBeTruthy();
    });
  });

  it('renders aggregate log and weird shape fallback gracefully', async () => {
    apis.getAlertSnapshots.mockResolvedValueOnce({
      snapshots: [
        {
          event_id: 'ev-agg',
          snapshot_time: '2026-09-16T10:00:00Z',
          query_clue: {
            policy_name: 'Traffic Spike',
            alert_type: 'aggregate',
          },
          raw_data: [
            { error_code: 500, spike_count: 88 },
            { error_code: 502, spike_count: 23 },
          ],
        },
      ],
    });

    render(<AlertRawLogWidget logAlertId="alert-agg" />);

    await waitFor(() => {
      expect(screen.getByText('Traffic Spike')).toBeTruthy();
      expect(screen.getByText('500')).toBeTruthy();
      expect(screen.getByText('88')).toBeTruthy();
      expect(screen.getByText('502')).toBeTruthy();
      expect(screen.getByText('23')).toBeTruthy();
    });
  });

  it('handles missing query clue and missing raw data states', async () => {
    apis.getAlertSnapshots.mockResolvedValueOnce({
      snapshots: [
        {
          event_id: 'ev-empty',
          snapshot_time: '2026-09-16T10:00:00Z',
          query_clue: null,
          raw_data: null,
        },
      ],
    });

    render(<AlertRawLogWidget logAlertId="alert-empty" />);

    await waitFor(() => {
      expect(screen.getByText('log.event.queryClueUnavailable')).toBeTruthy();
      expect(screen.getByText('log.event.rawDataUnavailable')).toBeTruthy();
    });
  });
});
