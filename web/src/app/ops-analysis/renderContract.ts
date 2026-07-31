export type DashboardWidgetRenderStatus =
  | 'loading'
  | 'ready'
  | 'empty'
  | 'failed';

export interface DashboardWidgetRenderResult {
  widgetId: string;
  status: DashboardWidgetRenderStatus;
  error?: string;
  /** Stable machine code for report-failed → RetryClassifier (optional). */
  errorCode?: string;
}

export interface DashboardRenderSignal {
  type: 'report-ready' | 'report-failed';
  dashboardId: string;
  widgets: DashboardWidgetRenderResult[];
  widgetId?: string;
  error?: string;
  errorCode?: string;
}

export const DASHBOARD_RENDER_EVENT = 'bk-dashboard-render';

export const isTerminalWidgetRenderStatus = (
  status: DashboardWidgetRenderStatus,
) => status !== 'loading';

export const hasRenderableWidgetData = (value: unknown): boolean => {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'string') return value.trim().length > 0;
  if (typeof value !== 'object') return true;

  const record = value as Record<string, unknown>;
  for (const key of ['items', 'results', 'data']) {
    if (Array.isArray(record[key])) {
      return record[key].length > 0;
    }
  }
  return Object.keys(record).length > 0;
};

export const buildDashboardRenderSignal = (
  dashboardId: string | number,
  widgetIds: string[],
  results: Map<string, DashboardWidgetRenderResult>,
): DashboardRenderSignal | null => {
  if (
    widgetIds.length === 0 ||
    widgetIds.some((widgetId) => {
      const result = results.get(widgetId);
      return !result || !isTerminalWidgetRenderStatus(result.status);
    })
  ) {
    return null;
  }

  const widgets = widgetIds.map((widgetId) => results.get(widgetId)!);
  const failed = widgets.find((result) => result.status === 'failed');

  return failed
    ? {
      type: 'report-failed',
      dashboardId: String(dashboardId),
      widgets,
      widgetId: failed.widgetId,
      error: failed.error || 'Widget render failed',
      ...(failed.errorCode ? { errorCode: failed.errorCode } : {}),
    }
    : {
      type: 'report-ready',
      dashboardId: String(dashboardId),
      widgets,
    };
};

export const emitDashboardRenderSignal = (signal: DashboardRenderSignal) => {
  window.dispatchEvent(
    new CustomEvent<DashboardRenderSignal>(DASHBOARD_RENDER_EVENT, {
      detail: signal,
    }),
  );
};
