'use client';

import React, { useMemo } from 'react';
import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
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
  /** 紧跟维度名的当前读数，例如「CPU 14.1%」「load1 0.88」。 */
  reading?: string;
  readingTone?: string;
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
  /** 标题旁的说明，悬停问号时展示。 */
  hint?: string;
  /** 嵌进已有卡片时不再套一层 panel。 */
  bare?: boolean;
  onRetry?: () => void;
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
  emptyText = '暂无数据',
  hint,
  bare = false,
  onRetry
}: ThinTimeSeriesProps) {
  const theme = useThemeColors();
  const axisColor = theme['--color-border'];
  const mutedColor = theme['--color-text-3'];
  const textColor = theme['--color-text-1'];
  const panelColor = theme['--color-bg'];
  const keys = useMemo(() => areaKeys(data), [data]);
  const option = useMemo(() => {
    if (!data.length || !keys.length) return null;
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
          lineStyle: { width: 1.6, color }
        };
      })
    };
  }, [axisColor, data, keys, legends, mutedColor, panelColor, textColor, unit]);
  const { containerRef } = useECharts(option);
  const showLegend = legends.length > 1 || legends.some((item) => item.reading);
  const chart = (
    <>
      {title || reading || showLegend ? (
        <div className={styles.chartHead}>
          {title || reading ? (
            <div className={styles.chartTitleGroup}>
              {title ? (
                <div className={styles.chartTitle}>
                  {hint ? (
                    <span className="inline-flex items-center gap-1">
                      {title}
                      <Tooltip title={hint} styles={{ body: { maxWidth: 360 } }}>
                        <QuestionCircleOutlined
                          className="cursor-help text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                          aria-label={hint}
                        />
                      </Tooltip>
                    </span>
                  ) : title}
                </div>
              ) : null}
              {reading ? (
                <div className={styles.chartReading} style={readingTone ? { color: readingTone } : undefined}>
                  {reading}
                </div>
              ) : null}
            </div>
          ) : null}
          {showLegend ? (
            <div className={styles.chartLegend}>
              {legends.map((item) => (
                <span key={item.label}>
                  <span
                    className={styles.legendSwatch}
                    style={{ background: item.color }}
                  />
                  {item.label}
                  {item.reading ? (
                    <span
                      className={styles.legendReading}
                      style={item.readingTone ? { color: item.readingTone } : undefined}
                    >
                      {item.reading}
                    </span>
                  ) : null}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className={styles.chartBody}>
        {loading || !data.length ? (
          <div className={styles.chartEmpty}>
            {loading ? '加载中' : emptyText}
            {!loading && onRetry ? (
              <button
                type="button"
                className="ml-2 text-[var(--color-primary)]"
                onClick={onRetry}
              >
                重试
              </button>
            ) : null}
          </div>
        ) : (
          <div ref={containerRef} className="h-full w-full" />
        )}
      </div>
    </>
  );

  if (bare) return <div className="min-w-0">{chart}</div>;
  return <section className={`${classic.panel} ${styles.chartPanel}`}>{chart}</section>;
}
