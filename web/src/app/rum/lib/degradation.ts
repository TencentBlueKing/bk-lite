export interface PipelineDegradation {
  controlUnavailable?: boolean;
  analyticsUnavailable?: boolean;
}

export type RumAnalyticsRange = '1h' | '24h' | '7d';

export type RumTraffic = 'visitors' | 'all' | 'automated' | 'bot' | 'synthetic';

export function degradationReason(
  page: PipelineDegradation | null | undefined,
): 'control' | 'analytics' | null {
  if (!page) return null;
  if (page.controlUnavailable) return 'control';
  if (page.analyticsUnavailable) return 'analytics';
  return null;
}

export function withDegradation<T extends object>(
  data: T & PipelineDegradation,
): T & PipelineDegradation {
  return {
    ...data,
    controlUnavailable: Boolean(data?.controlUnavailable),
    analyticsUnavailable: Boolean(data?.analyticsUnavailable),
  };
}
