'use client';

import { Progress } from 'antd';

import type { RumOverviewDistribution } from '@/app/rum/api';
import { useTranslation } from '@/utils/i18n';

export default function DistributionList({
  rows,
  strokeColor = '#0ea5e9',
  hoverTextClass = 'group-hover/dist:text-sky-600',
}: {
  rows: RumOverviewDistribution[];
  strokeColor?: string;
  hoverTextClass?: string;
}) {
  const { t } = useTranslation();
  const total = rows.reduce((sum, row) => sum + row.sessions, 0);

  if (rows.length === 0) {
    return (
      <div className="flex min-h-[80px] items-center justify-center">
        <p className="m-0 text-xs text-[var(--color-text-4)]">{t('rum.overview.noData', '当前窗口暂无数据')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {rows.map((row) => {
        const pct = total > 0 ? (row.sessions / total) * 100 : 0;
        const label =
          row.key === '(unknown)' ? t('rum.overview.unknown', '(未知)') : row.key;
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
