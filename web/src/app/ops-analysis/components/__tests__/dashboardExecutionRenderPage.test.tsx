import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';

import { DashboardExecutionRenderPageContent } from '@/app/ops-analysis/render/execution/[executionId]/dashboardExecutionRenderPage';

const api = {
  getExecutionRenderInput: vi.fn(),
};

const dashboardSpy = vi.fn();

vi.mock('@/app/ops-analysis/api/dashboardSubscription', () => ({
  useDashboardSubscriptionApi: () => api,
}));

vi.mock(
  '@/app/ops-analysis/(pages)/view/dashBoard',
  () => ({
    default: (props: unknown) => {
      dashboardSpy(props);
      return <div>dashboard-render</div>;
    },
  }),
);

const renderInput = {
  execution_id: 42,
  input_snapshot: {
    dashboard_id: 8,
    creator_id: 'test',
    subscription_id: 3,
    filter_values: { environment: 'production' },
    created_at: '2026-07-29T00:00:00Z',
  },
  render_snapshot: {
    dashboard_id: 8,
    dashboard_name: '冻结仪表盘',
    dashboard_updated_at: '2026-07-29T00:00:00Z',
    view_sets: [{ i: 'chart-1' }],
    filters: [{ id: 'environment' }],
    other: { title: '冻结标题' },
    widget_manifest: [
      {
        widget_id: 'chart-1',
        widget_type: 'line',
        datasource_id: 17,
      },
    ],
    created_at: '2026-07-29T00:00:01Z',
  },
};

beforeEach(() => {
  api.getExecutionRenderInput.mockResolvedValue(renderInput);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DashboardExecutionRenderPageContent', () => {
  it('loads frozen execution input and renders Dashboard in report mode', async () => {
    render(<DashboardExecutionRenderPageContent executionId={42} />);

    await waitFor(() => {
      expect(api.getExecutionRenderInput).toHaveBeenCalledWith(42);
      expect(dashboardSpy).toHaveBeenCalled();
    });

    const props = dashboardSpy.mock.calls.at(-1)?.[0];
    expect(props.renderMode).toBe(true);
    expect(props.renderFilterValues).toEqual({
      environment: 'production',
    });
    expect(props.selectedDashboard).toEqual({
      id: '8',
      data_id: '8',
      name: '冻结仪表盘',
      type: 'dashboard',
    });
    await expect(props.getDashboardDetailOverride(8)).resolves.toEqual({
      id: 8,
      name: '冻结仪表盘',
      updated_at: '2026-07-29T00:00:00Z',
      view_sets: [{ i: 'chart-1' }],
      filters: [{ id: 'environment' }],
      other: { title: '冻结标题' },
    });
  });

  it('publishes report-failed when render input cannot be loaded', async () => {
    api.getExecutionRenderInput.mockRejectedValueOnce(new Error('forbidden'));
    const signals: unknown[] = [];
    window.addEventListener('bk-dashboard-render', (event) => {
      signals.push((event as CustomEvent).detail);
    });

    render(<DashboardExecutionRenderPageContent executionId={42} />);

    await waitFor(() => {
      expect(signals).toEqual([
        {
          type: 'report-failed',
          dashboardId: '42',
          widgets: [],
          error: 'Render input load failed',
        },
      ]);
    });
    expect(dashboardSpy).not.toHaveBeenCalled();
  });
});
