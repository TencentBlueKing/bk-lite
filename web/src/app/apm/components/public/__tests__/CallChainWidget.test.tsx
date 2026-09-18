import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, t } = vi.hoisted(() => {
  const tFn = (key: string, defaultVal?: string) => defaultVal || key;
  return {
    t: tFn,
    api: {
      getService: vi.fn(),
      getTraces: vi.fn(),
    },
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (time: string) => `formatted-${time}`,
  }),
}));

vi.mock('@/app/apm/api', () => ({ default: () => api }));

import CallChainWidget from '../CallChainWidget';

const MOCK_SERVICE = {
  id: 'svc-checkout',
  name: 'checkout-service',
  language: 'go',
  namespace: 'order-system',
  application_name: 'Order App',
  status: 'active' as const,
  environment_views: [
    { environment: 'prod', last_seen_at: '2026-09-17T00:00:00Z', status: 'active' as const },
    { environment: 'staging', last_seen_at: '2026-09-17T00:00:00Z', status: 'active' as const },
  ],
};

const MOCK_TRACES_PROD = [
  {
    trace_id: 'trace-error-1111',
    started_at: '2026-09-17T02:10:00Z',
    duration_ms: 1250,
    service_namespace: 'order-system',
    service_name: 'checkout-service',
    environment: 'prod',
    instance_id: 'inst-1',
    status: 'error' as const,
    root_span_name: 'POST /api/v1/checkout',
    span_count: 8,
  },
  {
    trace_id: 'trace-ok-2222',
    started_at: '2026-09-17T02:15:00Z',
    duration_ms: 45,
    service_namespace: 'order-system',
    service_name: 'checkout-service',
    environment: 'prod',
    instance_id: 'inst-1',
    status: 'ok' as const,
    root_span_name: 'GET /api/v1/health',
    span_count: 2,
  },
];

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
  api.getTraces.mockResolvedValue({ items: MOCK_TRACES_PROD });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('CallChainWidget', () => {
  it('renders call chain table with endpoint, status tags, latency, span count and trace link', async () => {
    render(
      <CallChainWidget
        serviceId="svc-checkout"
        startedAt="2026-09-17T02:00:00Z"
        endedAt="2026-09-17T03:00:00Z"
      />,
    );

    // 1. Thin header with service and app info
    await waitFor(() => {
      expect(screen.getByText('checkout-service')).toBeTruthy();
      expect(screen.getByText('(Order App)')).toBeTruthy();
    });

    // 2. Endpoint as main column
    expect(screen.getByText('POST /api/v1/checkout')).toBeTruthy();
    expect(screen.getByText('GET /api/v1/health')).toBeTruthy();

    // 3. Status Tag
    expect(screen.getByText('apm.status.error')).toBeTruthy();
    expect(screen.getByText('apm.status.ok')).toBeTruthy();

    // 4. Span count
    expect(screen.getByText('8')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();

    // 5. Trace link
    const errorTraceLink = screen.getByText('trace-error-1111').closest('a');
    expect(errorTraceLink).toBeTruthy();
    expect(errorTraceLink?.getAttribute('href')).toBe('/apm/explore/traces/trace-error-1111');

    // 6. Open in explore button link with query params
    const exploreBtn = screen.getByText('apm.explore.openInExplore').closest('a');
    expect(exploreBtn).toBeTruthy();
    const href = exploreBtn?.getAttribute('href') || '';
    expect(href).toContain('/apm/explore/traces?');
    expect(href).toContain('service_name=checkout-service');
    expect(href).toContain('service_namespace=order-system');
  });

  it('filters by status via API parameter when user switches Segmented', async () => {
    render(
      <CallChainWidget
        serviceId="svc-checkout"
        startedAt="2026-09-17T02:00:00Z"
        endedAt="2026-09-17T03:00:00Z"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('POST /api/v1/checkout')).toBeTruthy();
    });

    // Switch to errorOnly
    const errorOnlyBtn = screen.getByText('apm.common.errorOnly');
    fireEvent.click(errorOnlyBtn);

    await waitFor(() => {
      expect(api.getTraces).toHaveBeenCalledWith(
        expect.objectContaining({
          service_name: 'checkout-service',
          status: 'error',
        }),
      );
    });

    // Switch back to all
    const allBtn = screen.getByText('apm.common.all');
    fireEvent.click(allBtn);

    await waitFor(() => {
      expect(api.getTraces).toHaveBeenLastCalledWith(
        expect.not.objectContaining({
          status: 'error',
        }),
      );
    });
  });

  it('switches environment and fetches traces for selected environment', async () => {
    render(
      <CallChainWidget
        serviceId="svc-checkout"
        startedAt="2026-09-17T02:00:00Z"
        endedAt="2026-09-17T03:00:00Z"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('POST /api/v1/checkout')).toBeTruthy();
    });

    const select = screen.getByRole('combobox');
    fireEvent.mouseDown(select);

    const stagingOption = await screen.findByTitle('staging');
    fireEvent.click(stagingOption);

    await waitFor(() => {
      expect(api.getTraces).toHaveBeenCalledWith(
        expect.objectContaining({
          environment: 'staging',
        }),
      );
    });
  });

  it('renders error state and retries successfully', async () => {
    api.getService.mockRejectedValueOnce(new Error('Network error'));

    render(<CallChainWidget serviceId="svc-checkout" />);

    await waitFor(() => {
      expect(screen.getByText('common.loadFailed')).toBeTruthy();
    });

    api.getService.mockResolvedValueOnce(MOCK_SERVICE);
    fireEvent.click(screen.getByText('common.retry'));

    await waitFor(() => {
      expect(screen.getByText('checkout-service')).toBeTruthy();
    });
  });
});
