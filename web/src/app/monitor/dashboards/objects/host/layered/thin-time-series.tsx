'use client';

import React, { useMemo } from 'react';
import dayjs from 'dayjs';
import { useECharts } from '../../../shared/widgets/useECharts';
import { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { CHART_COLORS } from '@/app/monitor/constants';
import { useThemeColors } from './theme-color';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export interface ThinLegend {
  label: string;
  color: string;
  dashed?: boolean;
}

export interface ThinReferenceLine {
  value: number;
  label: string;
  color: string;
}

interface ThinTimeSeriesProps {
  title: string;
  data: ChartData[];
  legends: ThinLegend[];
  unit?: MetricUnit;
  loading?: boolean;
  reading?: string;
  readingTone?: string;
  emptyText?: string;
  reference?: ThinReferenceLine | null;
}

const areaKeys = (data: ChartData[]) => {
  const keys = new Set<string>();
  data.forEach((point) => {
    Object.keys(point).forEach((key) => {
      if (key.startsWith('value')) keys.add(key);
    });
  });
  return Array.from(keys).sort();
};

const formatTooltipReading = (raw: unknown, unit: MetricUnit) => {
  const value = typeof raw === 'number' ? raw : Number.NaN;
  if (!Number.isFinite(value)) return '--';
  if (unit === 'none') return String(Number(value.toFixed(2)));
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

export default function ThinTimeSeries({
  title,
  data,
  legends,
  unit = 'none',
  loading = false,
  reading,
  readingTone,
  emptyText = '当前时间窗没有序列',
  reference
}: ThinTimeSeriesProps) {
  const theme = useThemeColors();
  const axisColor = theme['--color-border'];
  const mutedColor = theme['--color-text-3'];
  const textColor = theme['--color-text-1'];
  const panelColor = theme['--color-bg'];
  const keys = useMemo(() => areaKeys(data), [data]);
  const legendItems = useMemo(
    () => (reference ? [...legends, { label: reference.label, color: reference.color, dashed: true }] : legends),
    [legends, reference]
  );
  const option = useMemo(() => {
    if (!data.length || !keys.length) return null;
    const referenceValue = reference && Number.isFinite(reference.value) ? reference.value : null;
    return {
      animation: false,
      backgroundColor: 'transparent',
      grid: { top: 8, right: 10, bottom: 22, left: 44, containLabel: false },
      xAxis: {
        type: 'value' as const,
        min: 'dataMin' as const,
        max: 'dataMax' as const,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: axisColor } },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value' as const,
        ...(referenceValue != null ? {
          max: (extent: { max: number }) => {
            const top = Math.max(extent.max, referenceValue);
            if (!Number.isFinite(top)) return extent.max;
            return top <= 0 ? 1 : top * 1.08;
          }
        } : {}),
        axisLabel: {
          color: mutedColor,
          fontSize: 10,
          formatter: (value: number) => {
            const formatted = formatMetricValue(value, unit);
            return `${formatted.value}${formatted.unit || ''}`;
          }
        },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: axisColor, width: 1 } }
      },
      tooltip: {
        show: true,
        trigger: 'axis' as const,
        appendToBody: true,
        confine: false,
        backgroundColor: panelColor,
        borderColor: axisColor,
        borderWidth: 1,
        textStyle: { fontSize: 12, color: textColor },
        axisPointer: {
          type: 'line' as const,
          lineStyle: { color: mutedColor, width: 1, type: 'dashed' as const }
        },
        formatter: (params: any[]) => {
          if (!params.length) return '';
          const time = dayjs(Number(params[0].axisValue) * 1000).format('YYYY-MM-DD HH:mm:ss');
          const rows = params
            .map((item) => {
              const raw = Array.isArray(item.value) ? item.value[1] : item.value;
              const color = typeof item.color === 'string' ? item.color : 'var(--color-text-3)';
              const name = item.seriesName || '';
              return `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px"><span style="display:flex;align-items:center;gap:6px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span><span>${name}</span></span><span style="font-variant-numeric:tabular-nums;font-weight:600">${formatTooltipReading(raw, unit)}</span></div>`;
            })
            .join('');
          return `<div style="min-width:160px"><div style="margin-bottom:6px;color:var(--color-text-3)">${time}</div>${rows}</div>`;
        }
      },
      series: keys.map((key, index) => {
        const color = legends[index]?.color || CHART_COLORS[index % CHART_COLORS.length];
        return {
          type: 'line' as const,
          name: legends[index]?.label || key,
          showSymbol: false,
          symbol: 'none',
          smooth: 0.15,
          connectNulls: true,
          data: data.map((point) => {
            const value = point[key];
            return [point.time, typeof value === 'number' ? value : null];
          }),
          lineStyle: { width: 1.6, color },
          markLine: index === 0 && referenceValue != null ? {
            silent: true,
            symbol: ['none', 'none'],
            lineStyle: { type: 'dashed' as const, color: reference?.color, width: 1.2 },
            label: {
              show: true,
              formatter: reference?.label || '',
              color: mutedColor,
              fontSize: 10,
              position: 'insideEndTop' as const
            },
            data: [{ yAxis: referenceValue }]
          } : undefined
        };
      })
    };
  }, [axisColor, data, keys, legends, mutedColor, panelColor, reference, textColor, unit]);
  const { containerRef } = useECharts(option);

  return (
    <section className={`${classic.panel} ${styles.chartPanel}`}>
      <div className={styles.chartHead}>
        <div className={styles.chartTitle}>{title}</div>
        {reading ? (
          <div className={styles.chartReading} style={readingTone ? { color: readingTone } : undefined}>
            {reading}
          </div>
        ) : null}
        {legendItems.length > 1 ? (
          <div className={styles.chartLegend}>
            {legendItems.map((item) => (
              <span key={item.label}>
                <span
                  className={item.dashed ? styles.legendDashed : styles.legendSwatch}
                  style={item.dashed ? { borderTopColor: item.color } : { background: item.color }}
                />
                {item.label}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <div className={styles.chartBody}>
        {loading || !data.length ? (
          <div className={styles.chartEmpty}>{loading ? '加载中' : emptyText}</div>
        ) : (
          <div ref={containerRef} className="h-full w-full" />
        )}
      </div>
    </section>
  );
}
