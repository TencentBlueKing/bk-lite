import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DASHBOARD_RENDER_EVENT } from '@/app/ops-analysis/renderContract';
import { ScreenExecutionRenderPageContent } from '@/app/ops-analysis/render/execution/[executionId]/screenExecutionRenderPage';

const loadCanvasDataSources = vi.fn();
const getExecutionRenderInput = vi.fn();

vi.mock('@/app/ops-analysis/api/dashboardSubscription', () => ({
  useDashboardSubscriptionApi: () => ({
    getExecutionRenderInput,
  }),
}));

vi.mock('@/app/ops-analysis/hooks/useDataSource', () => ({
  useDataSourceManager: () => ({
    loadCanvasDataSources,
    dataSources: [{ id: 9, name: 'ds' }],
  }),
}));

const widgetStatusHandlers: Array<(result: unknown) => void> = [];

vi.mock(
  '@/app/ops-analysis/(pages)/view/screen/components/screenCanvas',
  () => ({
    default: (props: {
      onWidgetRenderStatus?: (result: unknown) => void;
      viewSets: { items?: Array<{ id: string }> };
    }) => {
      if (props.onWidgetRenderStatus) {
        widgetStatusHandlers.push(props.onWidgetRenderStatus);
      }
      return <div data-testid="screen-canvas" />;
    },
  }),
);

const baseRenderInput = {
  execution_id: 11,
  input_snapshot: {
    filter_values: {},
  },
  render_snapshot: {
    resource_type: 'screen',
    resource_id: 42,
    dashboard_id: null,
    filters: [],
    view_sets: {
      viewport: { width: 800, height: 600 },
      items: [{ id: 'w1', chartType: 'line', x: 0, y: 0, w: 100, h: 100 }],
    },
  },
};

describe('ScreenExecutionRenderPageContent ready contract', () => {
  beforeEach(() => {
    widgetStatusHandlers.length = 0;
    loadCanvasDataSources.mockReset();
    getExecutionRenderInput.mockReset();
    loadCanvasDataSources.mockResolvedValue(undefined);
    getExecutionRenderInput.mockResolvedValue(baseRenderInput);
  });

  afterEach(() => {
    cleanup();
  });

  it('does not emit report-ready before widget terminal status', async () => {
    const signals: string[] = [];
    const onSignal = (event: Event) => {
      signals.push((event as CustomEvent).detail.type);
    };
    window.addEventListener(DASHBOARD_RENDER_EVENT, onSignal);

    render(
      <ScreenExecutionRenderPageContent
        executionId={11}
        initialRenderInput={baseRenderInput as never}
      />,
    );

    await waitFor(() => {
      expect(loadCanvasDataSources).toHaveBeenCalled();
      expect(widgetStatusHandlers.length).toBeGreaterThan(0);
    });
    expect(signals).toEqual([]);

    window.removeEventListener(DASHBOARD_RENDER_EVENT, onSignal);
  });

  it('emits report-ready after all widgets reach terminal status', async () => {
    const signals: Array<{ type: string; widgets: unknown[] }> = [];
    const onSignal = (event: Event) => {
      signals.push((event as CustomEvent).detail);
    };
    window.addEventListener(DASHBOARD_RENDER_EVENT, onSignal);

    render(
      <ScreenExecutionRenderPageContent
        executionId={11}
        initialRenderInput={baseRenderInput as never}
      />,
    );

    await waitFor(() => {
      expect(widgetStatusHandlers.length).toBeGreaterThan(0);
    });
    widgetStatusHandlers[0]({ widgetId: 'w1', status: 'ready' });

    await waitFor(() => {
      expect(signals.some((item) => item.type === 'report-ready')).toBe(true);
    });

    window.removeEventListener(DASHBOARD_RENDER_EVENT, onSignal);
  });
});
