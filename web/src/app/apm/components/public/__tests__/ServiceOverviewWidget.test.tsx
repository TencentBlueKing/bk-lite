import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, t } = vi.hoisted(() => {
  const tFn = (key: string, defaultVal?: string) => defaultVal || key;
  return {
    t: tFn,
    api: {
      getService: vi.fn(),
      getServiceRed: vi.fn(),
    },
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t }),
}));

vi.mock('@/app/apm/api', () => ({ default: () => api }));

import ServiceOverviewWidget from '../ServiceOverviewWidget';

const MOCK_SERVICE = {
  id: 'svc-order',
  name: 'order-service',
  language: 'java',
  namespace: 'order-prod',
  application_name: 'Mall Backend',
  status: 'active' as const,
  environment_views: [
    { environment: 'prod', last_seen_at: '2026-09-17T00:00:00Z', status: 'active' as const },
    { environment: 'staging', last_seen_at: '2026-09-17T00:00:00Z', status: 'active' as const },
  ],
};

const MOCK_RED_PROD = {
  service_id: 'svc-order',
  environment: 'prod',
  started_at: '2026-09-17T02:00:00Z',
  ended_at: '2026-09-17T03:00:00Z',
  request_rate: 150.2,
  error_rate: 0.05,
  p95_ms: 120,
  p99_ms: 450,
  request_count: 540000,
  error_count: 27000,
  timeseries: [],
  top_endpoints: [
    {
      endpoint: 'POST /api/v1/orders',
      request_rate: 100.5,
      error_rate: 0.06,
      p95_ms: 110,
      p99_ms: 380,
    },
  ],
};

const MOCK_RED_STAGING = {
  service_id: 'svc-order',
  environment: 'staging',
  started_at: '2026-09-17T02:00:00Z',
  ended_at: '2026-09-17T03:00:00Z',
  request_rate: 10.0,
  error_rate: 0.0,
  p95_ms: 35,
  p99_ms: 60,
  request_count: 36000,
  error_count: 0,
  timeseries: [],
  top_endpoints: [],
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
  api.getService.mockResolvedValue(MOCK_SERVICE);
  api.getServiceRed.mockResolvedValue(MOCK_RED_PROD);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ServiceOverviewWidget', () => {
  it('renders service overview with rich header, RED cards, basic info, and top endpoints', async () => {
    render(
      <ServiceOverviewWidget
        serviceId="svc-order"
        startedAt="2026-09-17T02:00:00Z"
        endedAt="2026-09-17T03:00:00Z"
      />,
    );

    // 1. Header identity
    await waitFor(() => {
      expect(screen.getByText('order-service')).toBeTruthy();
      expect(screen.getByText('Mall Backend')).toBeTruthy();
      expect(screen.getByText('order-prod')).toBeTruthy();
    });

    // 2. Health dot / abnormal badge (since error_rate is 0.05)
    expect(screen.getByText('apm.health.abnormal')).toBeTruthy();
    expect(screen.getByText('Java')).toBeTruthy();

    // 3. Top endpoints table
    expect(screen.getByText('POST /api/v1/orders')).toBeTruthy();

    // 4. Detail link
    const detailLink = screen.getByText('apm.topology.openService').closest('a');
    expect(detailLink).toBeTruthy();
    expect(detailLink?.getAttribute('href')).toContain('/apm/services/svc-order');
  });

  it('allows switching environments and re-fetches RED metrics', async () => {
    api.getServiceRed.mockImplementation(
      (_id: string, env: string) => Promise.resolve(env === 'staging' ? MOCK_RED_STAGING : MOCK_RED_PROD),
    );

    render(
      <ServiceOverviewWidget
        serviceId="svc-order"
        startedAt="2026-09-17T02:00:00Z"
        endedAt="2026-09-17T03:00:00Z"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('POST /api/v1/orders')).toBeTruthy();
    });

    // Switch environment to staging
    const select = screen.getByRole('combobox');
    fireEvent.mouseDown(select);

    const stagingOption = await screen.findByTitle('staging');
    fireEvent.click(stagingOption);

    await waitFor(() => {
      expect(api.getServiceRed).toHaveBeenCalledWith(
        'svc-order',
        'staging',
        '2026-09-17T02:00:00.000Z',
        '2026-09-17T03:00:00.000Z',
      );
    });
  });

  it('renders error state and supports retry', async () => {
    api.getService.mockRejectedValueOnce(new Error('Network error'));

    render(<ServiceOverviewWidget serviceId="svc-order" />);

    await waitFor(() => {
      expect(screen.getByText('common.loadFailed')).toBeTruthy();
    });

    api.getService.mockResolvedValueOnce(MOCK_SERVICE);
    fireEvent.click(screen.getByText('common.retry'));

    await waitFor(() => {
      expect(screen.getByText('order-service')).toBeTruthy();
    });
  });
});
