'use client';

import { Popover, Progress } from 'antd';

import type { RumOverviewDistribution } from '@/app/rum/api';
import { useTranslation } from '@/utils/i18n';

/** Preview rows in the card; the rest open in a popover so the grid stays short. */
export const DISTRIBUTION_LIST_VISIBLE_ROWS = 2;

function DistributionRows({
  rows,
  total,
  strokeColor,
  hoverTextClass,
  unknownLabel,
}: {
  rows: RumOverviewDistribution[];
  total: number;
  strokeColor: string;
  hoverTextClass: string;
  unknownLabel: string;
}) {
  return (
    <div className="space-y-3">
      {rows.map((row) => {
        const pct = total > 0 ? (row.sessions / total) * 100 : 0;
        const label = row.key === '(unknown)' ? unknownLabel : row.key;
        return (
          <div key={row.key} className="group/dist space-y-1.5">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span
                className={['truncate font-medium text-[var(--color-text-2)] transition-colors', hoverTextClass]
                  .filter(Boolean)
                  .join(' ')}
                title={row.key}
              >
                {label}
              </span>
              <div className="shrink-0 font-mono text-[11px] tabular-nums">
                <span className="font-semibold text-[var(--color-text-1)]">{row.sessions}</span>
                <span className="mx-1.5 text-[var(--color-text-4)]">/</span>
                <span className="text-[var(--color-text-3)]">{pct.toFixed(0)}%</span>
              </div>
            </div>
            <Progress
              percent={Math.round(pct * 10) / 10}
              showInfo={false}
              strokeColor={strokeColor}
              trailColor="var(--color-fill-2)"
              size={[undefined, 5]}
              className="m-0 [&_.ant-progress-inner]:!bg-[var(--color-fill-2)]"
            />
          </div>
        );
      })}
    </div>
  );
}

export default function DistributionList({
  rows,
  title,
  strokeColor = 'var(--color-primary)',
  hoverTextClass = 'group-hover/dist:text-[var(--color-primary)]',
}: {
  rows: RumOverviewDistribution[];
  title?: string;
  strokeColor?: string;
  hoverTextClass?: string;
}) {
  const { t } = useTranslation();
  const total = rows.reduce((sum, row) => sum + row.sessions, 0);
  const unknownLabel = t('rum.overview.unknown', '(未知)');

  // Reserve 2 preview rows + action slot so all four cards share one body height.
  const bodyClass = 'flex min-h-[98px] flex-col justify-between gap-3';

  if (rows.length === 0) {
    return (
      <div className={`${bodyClass} items-center justify-center`}>
        <p className="m-0 text-xs text-[var(--color-text-4)]">{t('rum.overview.noData', '当前窗口暂无数据')}</p>
      </div>
    );
  }

  const overflow = rows.length - DISTRIBUTION_LIST_VISIBLE_ROWS;
  const previewRows =
    overflow > 0 ? rows.slice(0, DISTRIBUTION_LIST_VISIBLE_ROWS) : rows;

  return (
    <div className={bodyClass}>
      <DistributionRows
        rows={previewRows}
        total={total}
        strokeColor={strokeColor}
        hoverTextClass={hoverTextClass}
        unknownLabel={unknownLabel}
      />
      <div className="min-h-[18px]">
        {overflow > 0 ? (
          <Popover
            trigger="click"
            placement="bottomLeft"
            title={title || t('rum.overview.allItems', '全部')}
            content={
              <div className="max-h-[280px] w-[260px] overflow-y-auto overscroll-contain pr-1">
                <DistributionRows
                  rows={rows}
                  total={total}
                  strokeColor={strokeColor}
                  hoverTextClass={hoverTextClass}
                  unknownLabel={unknownLabel}
                />
              </div>
            }
          >
            <button
              type="button"
              className="w-full rounded-md border-0 bg-transparent px-0 py-0.5 text-left text-[11px] text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
            >
              {t('rum.overview.moreItems', '还有 {n} 项', { n: overflow })}
            </button>
          </Popover>
        ) : null}
      </div>
    </div>
  );
}
