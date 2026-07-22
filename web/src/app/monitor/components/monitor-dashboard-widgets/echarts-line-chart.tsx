'use client';

import React, { useMemo, useCallback, useRef } from 'react';
import dayjs, { type Dayjs } from 'dayjs';
import type { ChartData, MetricItem, MetricUnit } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import ChartSurface from '@/components/chart-surface';
import { useECharts } from '@/app/monitor/components/monitor-dashboard-widgets/useECharts';
import {
  formatMetricValue,
  normalizeGapIntervals,
} from '@/app/monitor/components/monitor-dashboard-widgets/runtime';

export interface EChartsLineChartProps {
  data: ChartData[];
  unit?: string;
  metric?: MetricItem;
  loading?: boolean;
  seriesStyles?: Array<{
    color?: string;
    strokeDasharray?: string;
    fillOpacity?: number;
    strokeOpacity?: number;
    strokeWidth?: number;
    unit?: string;
  }>;
  xAxisTimeFormat?: string;
  leftAxisWidthOverride?: number;
  allowSelect?: boolean;
  onXRangeChange?: (range: [Dayjs, Dayjs]) => void;
}

const DEFAULT_COLORS = [
  '#5B8FF9',
  '#5AD8A6',
  '#F6BD16',
  '#E86452',
  '#6DC8EC',
  '#945FB9',
  '#FF9845',
  '#1E9493',
];

const getChartAreaKeys = (arr: ChartData[]): string[] => {
  const keys = new Set<string>();
  arr.forEach((obj) => {
    Object.keys(obj).forEach((key) => {
      if (key.includes('value')) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys).sort();
};

const formatAxisNumber = (value: number) => {
  if (!Number.isFinite(value)) return '';
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Number.isInteger(value)) return `${value}`;
  return value.toFixed(2).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1');
};

const BINARY_SCALE_CONFIG: Record<string, string[]> = {
  bytes: ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'],
  kibibytes: ['KiB', 'MiB', 'GiB', 'TiB', 'PiB'],
  mebibytes: ['MiB', 'GiB', 'TiB', 'PiB'],
  gibibytes: ['GiB', 'TiB', 'PiB'],
  tebibytes: ['TiB', 'PiB'],
  byteps: ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'],
  kibyteps: ['KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'],
  mibyteps: ['MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'],
  gibyteps: ['GiB/s', 'TiB/s', 'PiB/s'],
  tibyteps: ['TiB/s', 'PiB/s'],
};

const resolveBinaryScale = (maxValue: number, metricUnit: string) => {
  const unitList = BINARY_SCALE_CONFIG[metricUnit];
  if (!unitList) return { divisor: 1, displayUnit: metricUnit };
  let divisor = 1;
  let idx = 0;
  while (maxValue / divisor >= 1024 && idx < unitList.length - 1) {
    divisor *= 1024;
    idx += 1;
  }
  return { divisor, displayUnit: unitList[idx] };
};

const EChartsLineChart: React.FC<EChartsLineChartProps> = ({
  data,
  unit = '',
  loading = false,
  seriesStyles = [],
  xAxisTimeFormat = 'HH:mm',
  leftAxisWidthOverride,
  allowSelect = true,
  onXRangeChange,
}) => {
  const dragStartRef = useRef<number | null>(null);

  const areaKeys = useMemo(() => getChartAreaKeys(data), [data]);
  const gapIntervals = useMemo(() => normalizeGapIntervals(data[0]?.gapIntervals || []), [data]);

  const details = useMemo(() => {
    return data.reduce<Record<string, Array<{ name: string; label: string; value: string }>>>(
      (pre, cur) => {
        return Object.assign(pre, cur.details);
      },
      {},
    );
  }, [data]);

  const option = useMemo(() => {
    if (!data.length || !areaKeys.length) return null;

    const yAxisUnit = seriesStyles[0]?.unit || unit || '';
    const needsBinaryScale = yAxisUnit in BINARY_SCALE_CONFIG;

    let scaleDivisor = 1;
    let scaleDisplayUnit = yAxisUnit;

    if (needsBinaryScale) {
      let maxValue = 0;
      data.forEach((point) => {
        areaKeys.forEach((key) => {
          const value = point[key];
          if (typeof value === 'number' && Number.isFinite(value)) {
            maxValue = Math.max(maxValue, Math.abs(value));
          }
        });
      });
      const scale = resolveBinaryScale(maxValue, yAxisUnit);
      scaleDivisor = scale.divisor;
      scaleDisplayUnit = scale.displayUnit;
    }

    const gapMarkArea: any = gapIntervals.length
      ? {
        silent: true,
        itemStyle: {
          color: 'rgba(245, 63, 63, 0.12)',
        },
        data: gapIntervals.map((gap) => [{ xAxis: gap.start }, { xAxis: gap.end }]),
      }
      : undefined;

    const seriesList = areaKeys.map((key, idx) => {
      const style = seriesStyles[idx] || {};
      const color = style.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
      const fillOpacity = style.fillOpacity ?? 0.05;
      const strokeOpacity = style.strokeOpacity ?? 1;
      const strokeWidth = style.strokeWidth ?? 2;
      const lineType: 'solid' | 'dashed' = style.strokeDasharray ? 'dashed' : 'solid';

      return {
        type: 'line' as const,
        name: key,
        connectNulls: true,
        data: data.map((datum) => {
          const value = datum[key] as number | null;
          if (value == null) return [datum.time, null];
          return [datum.time, scaleDivisor > 1 ? value / scaleDivisor : value];
        }),
        smooth: false,
        symbol: 'none',
        lineStyle: {
          width: strokeWidth,
          color,
          opacity: strokeOpacity,
          type: lineType,
        },
        areaStyle:
          fillOpacity > 0
            ? {
              color: {
                type: 'linear' as const,
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  {
                    offset: 0,
                    color: `${color}${Math.round(fillOpacity * 255)
                      .toString(16)
                      .padStart(2, '0')}`,
                  },
                  { offset: 1, color: `${color}03` },
                ],
              },
            }
            : undefined,
        emphasis: { disabled: true },
        markArea: idx === 0 ? gapMarkArea : undefined,
      };
    });

    const leftWidth = leftAxisWidthOverride || 50;

    return {
      animation: false,
      grid: {
        top: 12,
        right: 12,
        bottom: 24,
        left: leftWidth,
        containLabel: false,
      },
      xAxis: {
        type: 'value' as const,
        min: 'dataMin' as const,
        max: 'dataMax' as const,
        axisLabel: {
          formatter: (val: number) => dayjs(val * 1000).format(xAxisTimeFormat),
          fontSize: 11,
          color: '#8c8c8c',
        },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value' as const,
        axisLabel: {
          formatter: (val: number) => formatAxisNumber(val),
          fontSize: 11,
          color: '#8c8c8c',
        },
        splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' as const } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      tooltip: {
        trigger: 'axis' as const,
        backgroundColor: 'transparent',
        borderColor: 'transparent',
        borderWidth: 0,
        extraCssText: 'box-shadow:none;padding:0;background:transparent;',
        textStyle: { fontSize: 12, color: '#333' },
        formatter: (params: any[]) => {
          if (!params.length) return '';
          const time = dayjs(Number(params[0].axisValue) * 1000).format('YYYY-MM-DD HH:mm:ss');

          const timeKey = String(params[0].axisValue);
          const detailForTime = details[timeKey];

          if (detailForTime && detailForTime.length > 0) {
            return renderEChartsTooltipCard({
              title: time,
              rows: detailForTime.map((detail: { label: string; value: string }) => ({
                key: detail.label,
                markerShape: 'none',
                label: detail.label,
                value: detail.value,
              })),
            });
          }

          return renderEChartsTooltipCard({
            title: time,
            rows: params.flatMap((param: any, idx: number) => {
              const style = seriesStyles[idx] || {};
              const rawValue = Array.isArray(param.value) ? param.value[1] : param.value;
              if (rawValue == null) return [];

              let displayValue: string;
              let displayUnit: string;
              if (needsBinaryScale) {
                const numericValue = Number(rawValue);
                displayValue = numericValue >= 100 ? numericValue.toFixed(0) : numericValue.toFixed(1);
                displayUnit = scaleDisplayUnit;
              } else {
                const seriesUnit = style.unit || unit;
                const formatted = formatMetricValue(Number(rawValue), seriesUnit as MetricUnit);
                displayValue = formatted.value;
                displayUnit = formatted.unit;
              }

              const color = style.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
              return [
                {
                  key: `${param.seriesName || 'series'}-${idx}`,
                  color,
                  markerShape: 'circle' as const,
                  label: param.seriesName || `Series ${idx + 1}`,
                  value: [displayValue, displayUnit].filter(Boolean).join(' '),
                },
              ];
            }),
          });
        },
      },
      series: seriesList,
    };
  }, [data, areaKeys, seriesStyles, unit, xAxisTimeFormat, leftAxisWidthOverride, details, gapIntervals]);

  const handleZrMouseDown = useCallback(
    (params: any) => {
      if (!allowSelect || !onXRangeChange) return;
      dragStartRef.current = params.offsetX;
    },
    [allowSelect, onXRangeChange],
  );

  const handleZrMouseUp = useCallback(
    (params: any) => {
      if (!allowSelect || !onXRangeChange || dragStartRef.current == null) return;
      const startX = dragStartRef.current;
      const endX = params.offsetX;
      dragStartRef.current = null;

      if (Math.abs(endX - startX) < 10) return;

      const instance = getInstanceRef.current?.();
      if (!instance) return;

      const grid = instance.getModel().getComponent('grid', 0);
      if (!grid) return;
      const coordSys = (instance as any).getModel().getComponent('xAxis', 0);
      if (!coordSys) return;

      const xAxis = instance.convertFromPixel({ seriesIndex: 0 }, [Math.min(startX, endX), 0]);
      const xAxisEnd = instance.convertFromPixel({ seriesIndex: 0 }, [Math.max(startX, endX), 0]);

      if (xAxis && xAxisEnd) {
        const startTime = dayjs(Math.min(Number(xAxis[0]), Number(xAxisEnd[0])) * 1000);
        const endTime = dayjs(Math.max(Number(xAxis[0]), Number(xAxisEnd[0])) * 1000);
        if (startTime.isValid() && endTime.isValid() && !startTime.isSame(endTime)) {
          onXRangeChange([startTime, endTime]);
        }
      }
    },
    [allowSelect, onXRangeChange],
  );

  const getInstanceRef = useRef<(() => any) | null>(null);

  const { containerRef, getInstance } = useECharts(option, {
    onEvents:
      allowSelect && onXRangeChange
        ? {
          mousedown: handleZrMouseDown,
          mouseup: handleZrMouseUp,
        }
        : undefined,
  });

  getInstanceRef.current = getInstance;

  const isEmpty = !data.length || !areaKeys.length;
  const showLoading = isEmpty && loading;

  return (
    <ChartSurface
      hasData={!isEmpty}
      loading={showLoading}
      containerClassName="relative h-full w-full"
      emptyClassName="absolute inset-0"
    >
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
    </ChartSurface>
  );
};

export default EChartsLineChart;
