'use client';

import { useMemo } from 'react';
import { BarChartOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';

import type { RumSessionTrendPoint } from '@/app/rum/api';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';

/** Time-bucket histogram, matching core SessionTrendChart: discrete columns + hover. */
export default function SessionTrendChart({
  points,
  compact = false,
  hideTitle = false,
  asCard = false,
}: {
  points: RumSessionTrendPoint[];
  /** 嵌入双栏工作台时用更矮的趋势条 */
  compact?: boolean;
  hideTitle?: boolean;
  /** 卡片化外壳 */
  asCard?: boolean;
}) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const sessionsLabel = t('rum.sessions.trendSessions', '会话');
  const erroredLabel = t('rum.sessions.trendErrored', '出错');

  const rows = useMemo(() => {
    const span = (points.at(-1)?.atMs ?? points.at(-1)?.bucketStartMs ?? 0) - (points[0]?.atMs ?? points[0]?.bucketStartMs ?? 0);
    const tick = new Intl.DateTimeFormat(
      locale,
      span <= 36 * 3_600_000
        ? { hour: '2-digit', minute: '2-digit', hour12: false }
        : { month: 'short', day: 'numeric' },
    );
    return points.map((point, index) => {
      const atMs = Number(point.atMs ?? point.bucketStartMs) || 0;
      const total = Number(point.total ?? point.sessions) || 0;
      const errored = Math.min(total, Number(point.errored) || 0);
      return {
        key: `${atMs}-${index}`,
        atMs,
        bucket: atMs ? tick.format(new Date(atMs)) : '',
        total,
        errored,
        ok: total > errored ? total - errored : 0,
      };
    });
  }, [points, locale]);

  const max = Math.max(...rows.map((row) => row.total), 0);
  const chartH = compact ? 'h-16' : 'h-32';
  const emptyH = compact ? 'h-12' : 'h-24';

  const legend = (
    <div className="inline-flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-3)]">
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2 rounded-[2px] bg-[var(--color-primary)]" aria-hidden />
        {sessionsLabel}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2 rounded-[2px] bg-[var(--color-fail)]" aria-hidden />
        {erroredLabel}
      </span>
    </div>
  );

  const titleHeader = (
    <div className="flex items-center gap-2">
      <BarChartOutlined className="text-sm text-[var(--color-primary)]" />
      <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
        {t('rum.sessions.trend', '会话趋势')}
      </h2>
    </div>
  );

  if (points.length === 0) {
    const emptyContent = (
      <div className={`flex items-center justify-center ${emptyH}`}>
        <p className="m-0 text-sm text-[var(--color-text-3)]">
          {t('rum.sessions.trendEmpty', '范围内暂无会话样本')}
        </p>
      </div>
    );

    if (asCard) {
      return (
        <section className="min-w-0 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
          <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
            {titleHeader}
          </div>
          <div className="p-3.5">{emptyContent}</div>
        </section>
      );
    }

    return (
      <section className="min-w-0">
        {hideTitle ? null : (
          <div className="mb-2 flex min-h-8 items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-[var(--color-text-1)]">
              {t('rum.sessions.trend', '会话趋势')}
            </h2>
          </div>
        )}
        {emptyContent}
      </section>
    );
  }

  const yTicks = max > 0 ? [max, Math.round(max / 2), 0] : [0];

  const chartBody = (
    <div className="flex gap-2">
      {compact ? null : (
        <div
          className={`flex w-6 shrink-0 flex-col justify-between py-0.5 text-right text-[10px] tabular-nums text-[var(--color-text-3)] ${chartH}`}
        >
          {yTicks.map((tick, index) => (
            <span key={`y-${index}`}>{tick}</span>
          ))}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className={`relative ${chartH}`}>
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between">
            {yTicks.map((tick, index) => (
              <div key={`g-${index}`} className="border-t border-dashed border-[var(--color-border-2)]/60" />
            ))}
          </div>
          <div className="relative flex h-full items-end">
            {rows.map((row) => {
              const heightPct = max > 0 ? (row.total / max) * 100 : 0;
              return (
                <div key={row.key} className="h-full min-w-0 flex-1">
                  <Tooltip
                    mouseEnterDelay={0.05}
                    title={
                      <div className="flex flex-col gap-0.5 text-xs">
                        {row.bucket ? <span>{row.bucket}</span> : null}
                        <span className="tabular-nums">
                          {sessionsLabel} {row.total}
                        </span>
                        <span className="tabular-nums">
                          {erroredLabel} {row.errored}
                        </span>
                      </div>
                    }
                  >
                    <div
                      className="flex h-full w-full cursor-default items-end justify-center"
                      aria-label={`${row.bucket}, ${sessionsLabel} ${row.total}, ${erroredLabel} ${row.errored}`}
                    >
                      <div
                        className="flex w-[78%] flex-col-reverse overflow-hidden rounded-t"
                        style={{ height: heightPct > 0 ? `${heightPct}%` : 0 }}
                      >
                        {row.ok > 0 ? (
                          <div
                            className="bg-[var(--color-primary)] transition-colors hover:brightness-105"
                            style={{ height: `${(row.ok / row.total) * 100}%` }}
                          />
                        ) : null}
                        {row.errored > 0 ? (
                          <div
                            className="bg-[var(--color-fail)] transition-colors hover:brightness-105"
                            style={{ height: `${(row.errored / row.total) * 100}%` }}
                          />
                        ) : null}
                      </div>
                    </div>
                  </Tooltip>
                </div>
              );
            })}
          </div>
        </div>
        {compact ? null : (
          <div className="mt-1 flex">
            {rows.map((row) => (
              <span
                key={`${row.key}-label`}
                className="min-w-0 flex-1 truncate text-center text-[10px] text-[var(--color-text-3)]"
              >
                {row.bucket}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  if (asCard) {
    return (
      <section className="min-w-0 overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
          {titleHeader}
          {legend}
        </div>
        <div className="p-3.5">{chartBody}</div>
      </section>
    );
  }

  return (
    <section className="min-w-0">
      {hideTitle ? null : (
        <div className="mb-2 flex min-h-8 flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-[var(--color-text-1)]">
            {t('rum.sessions.trend', '会话趋势')}
          </h2>
          {legend}
        </div>
      )}
      {chartBody}
    </section>
  );
}
