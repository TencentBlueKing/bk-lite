'use client';

import type { RumApplicationHealthItem } from '@/app/rum/api';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import { appExperienceTone, cwvTone, formatPct } from '@/app/rum/lib/cwv';
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
          value: String(row.views),
          label: t('rum.analytics.kpiViews', '浏览'),
          onClick: onOpenViews,
        },
        {
          value: String(row.errors),
          label: t('rum.analytics.kpiErrors', '错误'),
          tone: row.errors > 0 ? 'danger' : 'success',
          onClick: onOpenErrors,
        },
        {
          value: formatPct(row.errorRate),
          label: t('rum.overview.kpiErrorRate', '错误率'),
          tone: errPct > 5 ? 'danger' : errPct > 0 ? 'warning' : 'success',
        },
        {
          value: row.lcpP75 > 0 ? `${Math.round(row.lcpP75)}ms` : '—',
          label: 'LCP P75',
          tone: cwvTone('lcp', row.lcpP75),
        },
        {
          value: row.inpP75 > 0 ? `${Math.round(row.inpP75)}ms` : '—',
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
  const poor = applications.filter(
    (a) => a.enabled && appExperienceTone(a.lcpP75, a.inpP75, a.errorRate) === 'danger',
  ).length;
  const sessions = applications.reduce((s, a) => s + a.sessions, 0);
  const views = applications.reduce((s, a) => s + a.views, 0);
  const errors = applications.reduce((s, a) => s + a.errors, 0);
  const worstLcp = applications.reduce((m, a) => Math.max(m, a.lcpP75), 0);
  const worstInp = applications.reduce((m, a) => Math.max(m, a.inpP75), 0);
  return (
    <RumMetricGrid
      cells={[
        {
          value: String(poor),
          label: t('rum.analytics.kpiPoorApps', '差体验应用'),
          tone: poor > 0 ? 'danger' : 'success',
        },
        { value: String(sessions), label: t('rum.analytics.kpiSessions', '会话') },
        { value: String(views), label: t('rum.analytics.kpiViews', '浏览') },
        {
          value: String(errors),
          label: t('rum.analytics.kpiErrors', '错误'),
          tone: errors > 0 ? 'danger' : 'success',
        },
        {
          value: worstLcp > 0 ? `${Math.round(worstLcp)}ms` : '—',
          label: t('rum.analytics.kpiWorstLcp', '最差 LCP'),
          tone: cwvTone('lcp', worstLcp),
        },
        {
          value: worstInp > 0 ? `${Math.round(worstInp)}ms` : '—',
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
