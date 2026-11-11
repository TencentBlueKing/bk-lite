'use client';

import type { RumApplicationHealthItem } from '@/app/rum/api';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import { appExperienceTone, cwvTone, formatMs, formatPct } from '@/app/rum/lib/cwv';
import { countText, maxKnown, sumKnown } from '@/app/rum/lib/metrics';
import { useTranslation } from '@/utils/i18n';

export function OverviewKpi({
  row,
  onOpenSessions,
  onOpenViews,
  onOpenErrors,
}: {
  row: RumApplicationHealthItem;
  onOpenSessions?: () => void;
  onOpenViews?: () => void;
  onOpenErrors?: () => void;
}) {
  const { t } = useTranslation();
  const errPct = Math.min(1, Math.max(0, row.errorRate)) * 100;
  return (
    <RumMetricGrid
      cells={[
        {
          value: String(row.sessions),
          label: t('rum.analytics.kpiSessions', '会话'),
          onClick: onOpenSessions,
        },
        {
          value: countText(row.views),
          label: t('rum.analytics.kpiViews', '浏览'),
          onClick: onOpenViews,
        },
        {
          value: countText(row.errors),
          label: t('rum.analytics.kpiErrors', '错误'),
          tone: row.errors == null ? undefined : row.errors > 0 ? 'danger' : 'success',
          onClick: onOpenErrors,
        },
        {
          value: formatPct(row.errorRate),
          label: t('rum.overview.kpiErrorRate', '错误率'),
          tone: errPct > 5 ? 'danger' : errPct > 0 ? 'warning' : 'success',
        },
        {
          value: formatMs(row.lcpP75),
          label: 'LCP P75',
          tone: cwvTone('lcp', row.lcpP75),
        },
        {
          value: formatMs(row.inpP75),
          label: 'INP P75',
          tone: cwvTone('inp', row.inpP75),
        },
      ]}
    />
  );
}

export function CatalogKpi({
  applications,
}: {
  applications: RumApplicationHealthItem[];
}) {
  const { t } = useTranslation();
  const enabled = applications.filter((a) => a.enabled);
  const poor = enabled.filter(
    (a) => appExperienceTone(a.lcpP75, a.inpP75, a.errorRate) === 'danger',
  ).length;
  const sessions = enabled.reduce((s, a) => s + a.sessions, 0);
  const views = sumKnown(enabled.map((a) => a.views));
  const errors = sumKnown(enabled.map((a) => a.errors));
  const worstLcp = maxKnown(enabled.map((a) => a.lcpP75));
  const worstInp = maxKnown(enabled.map((a) => a.inpP75));
  return (
    <RumMetricGrid
      cells={[
        {
          value: String(poor),
          label: t('rum.analytics.kpiPoorApps', '差体验应用'),
          tone: poor > 0 ? 'danger' : 'success',
        },
        { value: String(sessions), label: t('rum.analytics.kpiSessions', '会话') },
        { value: countText(views), label: t('rum.analytics.kpiViews', '浏览') },
        {
          value: countText(errors),
          label: t('rum.analytics.kpiErrors', '错误'),
          tone: errors == null ? undefined : errors > 0 ? 'danger' : 'success',
        },
        {
          value: formatMs(worstLcp),
          label: t('rum.analytics.kpiWorstLcp', '最差 LCP'),
          tone: cwvTone('lcp', worstLcp),
        },
        {
          value: formatMs(worstInp),
          label: t('rum.analytics.kpiWorstInp', '最差 INP'),
          tone: cwvTone('inp', worstInp),
        },
      ]}
    />
  );
}

export function SessionKpi({
  total,
  errored,
  medianDuration,
  onToggleErrors,
}: {
  total: number;
  errored: number;
  medianDuration: string;
  onToggleErrors?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <RumMetricGrid
      cells={[
        { value: String(total), label: t('rum.sessions.kpi.total', '全部会话') },
        {
          value: String(errored),
          label: t('rum.sessions.kpi.errored', '错误会话'),
          tone: errored > 0 ? 'danger' : 'success',
          onClick: onToggleErrors,
        },
        {
          value: medianDuration,
          label: t('rum.sessions.kpi.medianDuration', '中位时长'),
        },
      ]}
    />
  );
}
