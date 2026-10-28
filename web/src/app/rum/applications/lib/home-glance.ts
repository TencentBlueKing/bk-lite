import type { RumApplicationHealthItem } from '@/app/rum/api';
import { appExperienceTone } from '@/app/rum/lib/cwv';

export type GlanceKind = 'poor' | 'watch' | 'observing' | 'empty';

export function glanceKind(app: RumApplicationHealthItem): GlanceKind {
  if (!app.enabled || app.sessions <= 0) return 'empty';
  const tone = appExperienceTone(app.lcpP75, app.inpP75, app.errorRate);
  if (tone === 'danger') return 'poor';
  if (tone === 'warning') return 'watch';
  if (tone === 'neutral') return 'empty';
  return 'observing';
}

export function homeGlance(apps: RumApplicationHealthItem[]) {
  const counts: Record<GlanceKind, number> = { poor: 0, watch: 0, observing: 0, empty: 0 };
  let topError: RumApplicationHealthItem | null = null;
  let worstLcp: RumApplicationHealthItem | null = null;
  for (const app of apps) {
    counts[glanceKind(app)] += 1;
    if (app.sessions > 0 && (!topError || app.errorRate > topError.errorRate)) topError = app;
    if (app.lcpP75 > 0 && (!worstLcp || app.lcpP75 > worstLcp.lcpP75)) worstLcp = app;
  }
  return { total: apps.length, counts, topError, worstLcp };
}
