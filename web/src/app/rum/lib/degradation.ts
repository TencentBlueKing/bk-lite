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

/** One banner per flag. Both can be true at once; order is control then analytics. */
export function degradationBanners(
  page: PipelineDegradation | null | undefined,
): Array<'control' | 'analytics'> {
  if (!page) return [];
  const banners: Array<'control' | 'analytics'> = [];
  if (page.controlUnavailable) banners.push('control');
  if (page.analyticsUnavailable) banners.push('analytics');
  return banners;
}

/**
 * Empty list/chart copy follows the analytics sentence only when that plane is down.
 * A successful empty result keeps the page's own copy, even if control is also down.
 */
export function listEmptyUsesAnalyticsCopy(
  page: PipelineDegradation | null | undefined,
): boolean {
  return Boolean(page?.analyticsUnavailable);
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
