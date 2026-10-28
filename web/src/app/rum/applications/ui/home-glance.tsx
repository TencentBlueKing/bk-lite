'use client';

import Link from 'next/link';

import type { RumApplicationHealthItem } from '@/app/rum/api';
import { homeGlance, type GlanceKind } from '@/app/rum/applications/lib/home-glance';
import { formatMs, formatPct } from '@/app/rum/lib/cwv';
import { useTranslation } from '@/utils/i18n';

const KIND_CLASS: Record<GlanceKind, string> = {
  poor: 'bg-[var(--color-fail)]',
  watch: 'bg-[var(--theme-color-status-warning)]',
  observing: 'bg-[var(--color-success)]',
  empty: 'bg-[var(--color-fill-3)]',
};

export default function HomeGlance({
  applications,
  hrefFor,
}: {
  applications: RumApplicationHealthItem[];
  hrefFor: (app: RumApplicationHealthItem) => string;
}) {
  const { t } = useTranslation();
  const glance = homeGlance(applications);
  const kinds: { kind: GlanceKind; label: string }[] = [
    { kind: 'poor', label: t('rum.analytics.health.danger', '差') },
    { kind: 'watch', label: t('rum.analytics.health.warning', '需关注') },
    { kind: 'observing', label: t('rum.analytics.health.success', '观察中') },
    { kind: 'empty', label: t('rum.analytics.health.neutral', '无样本') },
  ];
  return (
    <div className="mb-2 mt-4 grid shrink-0 gap-2 md:grid-cols-3">
      <section className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3">
        <div className="mb-2 text-[12px] font-medium text-[var(--color-text-2)]">
          {t('rum.applications.glanceDistribution', '应用体验分布')}
        </div>
        <div className="flex flex-col gap-1.5 text-[12px] text-[var(--color-text-2)]">
          {kinds.map((item) => (
            <div key={item.kind} className="flex items-center gap-2">
              <span className={`size-2 rounded-full ${KIND_CLASS[item.kind]}`} />
              <span className="min-w-0 flex-1">{item.label}</span>
              <span className="tabular-nums">{glance.counts[item.kind]}</span>
            </div>
          ))}
        </div>
      </section>
      <GlancePick
        title={t('rum.applications.glanceTopError', '错误率最高')}
        app={glance.topError}
        hrefFor={hrefFor}
        detail={glance.topError ? formatPct(glance.topError.errorRate) : '—'}
      />
      <GlancePick
        title={t('rum.applications.glanceWorstLcp', '最差 LCP')}
        app={glance.worstLcp}
        hrefFor={hrefFor}
        detail={glance.worstLcp ? formatMs(glance.worstLcp.lcpP75) : '—'}
      />
    </div>
  );
}

function GlancePick({
  title,
  app,
  hrefFor,
  detail,
}: {
  title: string;
  app: RumApplicationHealthItem | null;
  hrefFor: (app: RumApplicationHealthItem) => string;
  detail: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3">
      <div className="mb-2 text-[12px] font-medium text-[var(--color-text-2)]">{title}</div>
      {app ? (
        <Link href={hrefFor(app)} className="font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]">
          {app.application}
          <span className="ml-2 font-mono tabular-nums text-[var(--color-text-2)]">{detail}</span>
        </Link>
      ) : (
        <span className="text-[var(--color-text-3)]">—</span>
      )}
    </section>
  );
}
