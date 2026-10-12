'use client';

import React, { useMemo } from 'react';
import { useECharts } from '../../../shared/widgets/useECharts';
import { ChartData } from '@/app/monitor/types';
import styles from './layered.module.scss';

export interface SignalItem {
  key: string;
  label: string;
  value: string;
  color: string;
  tone?: string;
  trend: ChartData[];
}

const Spark = ({ data, color }: { data: ChartData[]; color: string }) => {
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
          lineStyle: { width: 1.4, color },
          areaStyle: { opacity: 0 }
        }
      ]
    };
  }, [color, series]);
  const { containerRef } = useECharts(option);
  if (!option) return <div className={styles.signalSpark} />;
  return <div ref={containerRef} className={styles.signalSpark} />;
};

export default function SignalBar({
  items,
  alertCount
}: {
  items: SignalItem[];
  alertCount: number | null;
}) {
  return (
    <div className={styles.signalBar}>
      {items.map((item) => (
        <div key={item.key} className={styles.signalPill}>
          <div>
            <div className={styles.signalLabel}>{item.label}</div>
            <div className={styles.signalValue} style={{ color: item.tone || item.color }}>
              {item.value}
            </div>
          </div>
          <Spark data={item.trend} color={item.color} />
        </div>
      ))}
      {alertCount != null ? (
        <div className={`${styles.signalPill} ${styles.alertPill}`}>
          <div>
            <div className={styles.alertValue}>{alertCount}</div>
            <div className={styles.alertHint}>告警 / 异常</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
