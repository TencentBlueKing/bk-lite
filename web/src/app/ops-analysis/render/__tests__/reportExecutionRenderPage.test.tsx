import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';

import { ReportExecutionRenderPageContent } from '@/app/ops-analysis/render/execution/[executionId]/reportExecutionRenderPage';

const api = {
  getExecutionRenderInput: vi.fn(),
};

const reportSpy = vi.fn();

vi.mock('@/app/ops-analysis/api/dashboardSubscription', () => ({
  useDashboardSubscriptionApi: () => api,
}));

vi.mock(
  '@/app/ops-analysis/(pages)/view/report',
  () => ({
    default: (props: unknown) => {
      reportSpy(props);
      return <div>report-render</div>;
    },
  }),
);

const renderInput = {
  execution_id: 51,
  input_snapshot: {
    dashboard_id: null,
    resource_type: 'report',
    resource_id: 9,
    creator_id: 'test',
    subscription_id: 4,
    filter_values: { billing_period: '2026-07' },
    created_at: '2026-08-17T00:00:00Z',
  },
  render_snapshot: {
    dashboard_id: null,
    dashboard_name: '冻结报表',
    dashboard_updated_at: '2026-08-17T00:00:00Z',
    resource_type: 'report',
    resource_id: 9,
    view_sets: {
      schema_version: 1,
      filters: [{ id: 'billing_period' }],
      sections: [{ id: 's1', valueConfig: { chartType: 'table' } }],
    },
    filters: [{ id: 'billing_period' }],
    other: {},
    widget_manifest: [
      {
        widget_id: 's1',
        widget_type: 'table',
        datasource_id: 3,
      },
    ],
    created_at: '2026-08-17T00:00:01Z',
  },
};

beforeEach(() => {
  api.getExecutionRenderInput.mockResolvedValue(renderInput);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ReportExecutionRenderPageContent', () => {
  it('renders Report in renderMode from frozen execution input', async () => {
    render(
      <ReportExecutionRenderPageContent
        executionId={51}
        initialRenderInput={renderInput as never}
      />,
    );

    await waitFor(() => {
      expect(reportSpy).toHaveBeenCalled();
    });
    expect(api.getExecutionRenderInput).not.toHaveBeenCalled();

    const props = reportSpy.mock.calls.at(-1)?.[0];
    expect(props.renderMode).toBe(true);
    expect(props.renderFilterValues).toEqual({
      billing_period: '2026-07',
    });
    expect(props.selectedReport).toEqual({
      id: '9',
      data_id: '9',
      name: '冻结报表',
      type: 'report',
    });
    await expect(props.getReportDetailOverride(9)).resolves.toEqual({
      id: 9,
      name: '冻结报表',
      updated_at: '2026-08-17T00:00:00Z',
      view_sets: renderInput.render_snapshot.view_sets,
      refresh_interval: 0,
    });
  });
});
