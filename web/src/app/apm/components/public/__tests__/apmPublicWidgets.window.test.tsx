import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, t } = vi.hoisted(() => {
  const tFn = (key: string, defaultVal?: string) => defaultVal || key;
  return {
    t: tFn,
    api: {
      getService: vi.fn(),
      getServiceRed: vi.fn(),
      getTraces: vi.fn(),
    },
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (time: string) => time,
  }),
}));

vi.mock('@/app/apm/api', () => ({ default: () => api }));

import CallChainWidget from '../CallChainWidget';
import ServiceOverviewWidget from '../ServiceOverviewWidget';

const SERVICE = {
  id: 'svc-1',
  name: 'checkout',
  namespace: 'shop',
  application_name: 'Shop',
  environment_views: [{ environment: 'prod' }],
};

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
});

beforeEach(() => {
  api.getService.mockResolvedValue(SERVICE);
  api.getServiceRed.mockResolvedValue({
    environment: 'prod',
    request_rate: 1,
    error_rate: 0,
    p95_ms: 12,
  });
  api.getTraces.mockResolvedValue({
    items: [
      {
        trace_id: 't1',
        started_at: '2026-09-16T10:00:00.000Z',
        duration_ms: 20,
        status: 'ok',
      },
    ],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM public widgets query window', () => {
  it('ServiceOverviewWidget passes host window into getServiceRed', async () => {
    render(
      <ServiceOverviewWidget
        serviceId="svc-1"
        startedAt="2026-09-16T09:30:00.000Z"
        endedAt="2026-09-16T10:30:00.000Z"
      />,
    );

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalledWith(
        'svc-1',
        'prod',
        '2026-09-16T09:30:00.000Z',
        '2026-09-16T10:30:00.000Z',
      );
    });
  });

  it('CallChainWidget passes host window into getTraces', async () => {
    render(
      <CallChainWidget
        serviceId="svc-1"
        startedAt="2026-09-16T09:30:00.000Z"
        endedAt="2026-09-16T10:30:00.000Z"
      />,
    );

    await waitFor(() => {
      expect(api.getTraces).toHaveBeenCalledWith(
        expect.objectContaining({
          started_at: '2026-09-16T09:30:00.000Z',
          ended_at: '2026-09-16T10:30:00.000Z',
          limit: 20,
        }),
      );
    });
  });

  it('falls back to a one-hour lookback ending near now when the host omits the window', async () => {
    const before = Date.now();
    render(<ServiceOverviewWidget serviceId="svc-1" />);
    render(<CallChainWidget serviceId="svc-1" />);

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalled();
      expect(api.getTraces).toHaveBeenCalled();
    });

    const after = Date.now();
    const redStarted = Date.parse(api.getServiceRed.mock.calls[0][2] as string);
    const redEnded = Date.parse(api.getServiceRed.mock.calls[0][3] as string);
    expect(redEnded - redStarted).toBe(60 * 60 * 1000);
    expect(redEnded).toBeGreaterThanOrEqual(before);
    expect(redEnded).toBeLessThanOrEqual(after);

    const tracesArgs = api.getTraces.mock.calls[0][0] as {
      started_at: string;
      ended_at: string;
    };
    expect(Date.parse(tracesArgs.ended_at) - Date.parse(tracesArgs.started_at)).toBe(
      60 * 60 * 1000,
    );
  });
});
