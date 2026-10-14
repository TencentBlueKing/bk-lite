'use client';

import React, { useMemo } from 'react';
import { Tooltip } from 'antd';
import { useECharts } from '../../../shared/widgets/useECharts';
import { ChartData } from '@/app/monitor/types';
import { resolveThemeColor, useThemeColors } from './theme-color';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export const Spark = ({
  data,
  color,
  className
}: {
  data: ChartData[];
  color: string;
  className?: string;
}) => {
  const theme = useThemeColors();
  const stroke = resolveThemeColor(color, theme) || theme['--color-text-3'];
  const series = useMemo(
    () =>
      data
        .map((point) => {
          const values = Object.entries(point)
            .filter(([key, value]) => key.startsWith('value') && typeof value === 'number')
            .map(([, value]) => value as number);
          return [Number(point.time), values[0]] as [number, number | undefined];
        })
        .filter((item): item is [number, number] => Number.isFinite(item[0]) && Number.isFinite(item[1])),
    [data]
  );
  const option = useMemo(() => {
    if (series.length < 2) return null;
    return {
      animation: false,
      grid: { top: 2, right: 0, bottom: 2, left: 0 },
      xAxis: { type: 'value' as const, show: false, min: series[0][0], max: series[series.length - 1][0] },
      yAxis: { type: 'value' as const, show: false },
      series: [
        {
          type: 'line' as const,
          data: series,
          showSymbol: false,
          symbol: 'none',
          lineStyle: { width: 1.4, color: stroke }
        }
      ]
    };
  }, [series, stroke]);
  const { containerRef } = useECharts(option);
  if (!option) return <div className={className || classic.miniTrend} />;
  return <div ref={containerRef} className={className || classic.miniTrend} />;
};

export const FlatSpark = ({ className }: { className?: string }) => (
  <div className={className || styles.flatSpark} aria-hidden="true">
    <span className={styles.flatSparkLine} />
  </div>
);

export interface KpiCardModel {
  key: string;
  label: string;
  /** 窄卡保留短标题时，悬浮展示完整名称。 */
  hint?: string;
  value: string;
  color: string;
  tone?: string;
  subtitle?: string;
  detail?: string;
  trend?: ChartData[];
  flat?: boolean;
  extra?: React.ReactNode;
  onActivate?: () => void;
  expanded?: boolean;
}

const KpiCardBody = ({ item }: { item: KpiCardModel }) => (
  <>
    <div className={classic.statLabel}>
      {item.hint ? (
        <Tooltip title={item.hint}>
          <span>{item.label}</span>
        </Tooltip>
      ) : item.label}
    </div>
    <div className={classic.statBody}>
      <div className={classic.statValue} style={item.tone ? { color: item.tone } : undefined}>
        {item.value}
        {item.subtitle ? <span className={classic.statUnit}>{item.subtitle}</span> : null}
      </div>
      {item.detail ? <div className={classic.statMeta}>{item.detail}</div> : null}
      {item.extra}
    </div>
    {item.flat ? <FlatSpark /> : <Spark data={item.trend || []} color={item.color} />}
  </>
);

/** 概览 KPI：值 + 细 spark。告警没有历史时序时只画平线。 */
export function KpiStrip({ items }: { items: KpiCardModel[] }) {
  return (
    <div className={styles.kpiGrid}>
      {items.map((item) => (
        item.onActivate ? (
          <button
            key={item.key}
            type="button"
            className={`${classic.statCard} ${styles.kpiActivate}`}
            onClick={item.onActivate}
            aria-expanded={Boolean(item.expanded)}
            aria-haspopup="dialog"
          >
            <KpiCardBody item={item} />
          </button>
        ) : (
          <div key={item.key} className={classic.statCard}>
            <KpiCardBody item={item} />
          </div>
        )
      ))}
    </div>
  );
}
