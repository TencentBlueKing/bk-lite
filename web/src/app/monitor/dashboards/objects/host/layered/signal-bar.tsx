'use client';

import React, { useMemo } from 'react';
import { useECharts } from '../../../shared/widgets/useECharts';
import { ChartData } from '@/app/monitor/types';
import { resolveThemeColor, useThemeColors } from './theme-color';
import styles from './layered.module.scss';

export interface SignalItem {
  key: string;
  label: string;
  value: string;
  color: string;
  tone?: string;
  subtitle?: string;
  trend: ChartData[];
}

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
  if (!option) return <div className={className || styles.signalSpark} />;
  return <div ref={containerRef} className={className || styles.signalSpark} />;
};

export default function SignalBar({
  items,
  alertCount
}: {
  items: SignalItem[];
  alertCount: number | null;
}) {
  const alertTone = alertCount == null
    ? undefined
    : alertCount === 0
      ? 'var(--color-success)'
      : 'var(--color-fail)';
  return (
    <div className={styles.signalBar}>
      {items.map((item) => (
        <div key={item.key} className={styles.signalPill}>
          <div>
            <div className={styles.signalLabel}>{item.label}</div>
            <div className={styles.signalValue} style={{ color: item.tone || undefined }}>
              {item.value}
            </div>
            {item.subtitle ? <div className={styles.signalSub}>{item.subtitle}</div> : null}
          </div>
          <Spark data={item.trend} color={item.color} />
        </div>
      ))}
      <div className={styles.alertBox}>
        <div className={styles.alertK}>告警 / 异常</div>
        <div className={styles.alertValue} style={{ color: alertTone }}>
          {alertCount == null ? '--' : `${alertCount}个`}
        </div>
      </div>
    </div>
  );
}
