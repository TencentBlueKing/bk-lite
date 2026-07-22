'use client';

import React, { useMemo, useCallback, useRef } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { Empty, Spin } from 'antd';
import { ChartData, MetricItem } from '@/app/monitor/types';
import { useECharts } from './useECharts';
import { formatMetricValue } from '../utils/format';
import { MetricUnit } from '../types';
import { normalizeGapIntervals } from '@/app/monitor/utils/gapIntervals';
import { CHART_COLORS } from '@/app/monitor/constants';
import { roundChartValueToDisplayPrecision } from './chart-display-precision';

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
  tibyteps: ['TiB/s', 'PiB/s']
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
  onXRangeChange
}) => {
  const dragStartRef = useRef<number | null>(null);

  const areaKeys = useMemo(() => getChartAreaKeys(data), [data]);
  const gapIntervals = useMemo(
    () => normalizeGapIntervals(data[0]?.gapIntervals || []),
    [data]
  );

  const details = useMemo(() => {
    return data.reduce<Record<string, Array<{ name: string; label: string; value: string }>>>((pre, cur) => {
      return Object.assign(pre, cur.details);
    }, {});
  }, [data]);

  const option = useMemo(() => {
    if (!data.length || !areaKeys.length) return null;

    const yAxisUnit = seriesStyles[0]?.unit || unit || '';
    const needsBinaryScale = yAxisUnit in BINARY_SCALE_CONFIG;
    const displayValues = data.flatMap((point) => areaKeys.map((key) => point[key] as number | null));
    const allSeriesValuesAreZero = displayValues.some((value) => value != null)
      && displayValues.every((value) => value == null || roundChartValueToDisplayPrecision(value) === 0);

    let scaleDivisor = 1;
    let scaleDisplayUnit = yAxisUnit;

    if (needsBinaryScale) {
      let maxValue = 0;
      data.forEach((point) => {
        areaKeys.forEach((key) => {
          const v = point[key];
          if (typeof v === 'number' && Number.isFinite(v)) {
            maxValue = Math.max(maxValue, Math.abs(v));
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
          color: 'rgba(245, 63, 63, 0.12)'
        },
        data: gapIntervals.map((gap) => [
          { xAxis: gap.start },
          { xAxis: gap.end }
        ])
      }
      : undefined;

    const seriesList = areaKeys.map((key, idx) => {
      const style = seriesStyles[idx] || {};
      const color = style.color || CHART_COLORS[idx % CHART_COLORS.length];
      const fillOpacity = style.fillOpacity ?? 0.05;
      const strokeOpacity = style.strokeOpacity ?? 1;
      const strokeWidth = style.strokeWidth ?? 2;
      // 数据线一律实线，多系列靠颜色区分；仅显式 strokeDasharray（阈值/上限线，由 style:'limit' 注入）才虚线。
      const lineType: 'solid' | 'dashed' = style.strokeDasharray ? 'dashed' : 'solid';

      return {
        type: 'line' as const,
        name: key,
        connectNulls: true,
        data: data.map((d) => {
          const v = d[key] as number | null;
          if (v == null) return [d.time, null];
          const scaledValue = scaleDivisor > 1 ? v / scaleDivisor : v;
          return [d.time, roundChartValueToDisplayPrecision(scaledValue)];
        }),
        smooth: false,
        symbol: 'none',
        lineStyle: {
          width: strokeWidth,
          color,
          opacity: strokeOpacity,
          type: lineType
        },
        areaStyle: fillOpacity > 0 ? {
          color: {
            type: 'linear' as const,
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: `${color}${Math.round(fillOpacity * 255).toString(16).padStart(2, '0')}` },
              { offset: 1, color: `${color}03` }
            ]
          }
        } : undefined,
        emphasis: { disabled: true },
        markArea: idx === 0 ? gapMarkArea : undefined
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
        containLabel: false
      },
      xAxis: {
        type: 'value' as const,
        min: 'dataMin' as const,
        max: 'dataMax' as const,
        axisLabel: {
          formatter: (val: number) => dayjs(val * 1000).format(xAxisTimeFormat),
          fontSize: 11,
          color: '#8c8c8c'
        },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value' as const,
        min: allSeriesValuesAreZero ? 0 : undefined,
        max: allSeriesValuesAreZero ? 1 : undefined,
        axisLabel: {
          formatter: (val: number) => allSeriesValuesAreZero && val !== 0 ? '' : formatAxisNumber(val),
          fontSize: 11,
          color: '#8c8c8c'
        },
        splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' as const } },
        axisLine: { show: false },
        axisTick: { show: false }
      },
      tooltip: {
        trigger: 'axis' as const,
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: '#e8e8e8',
        borderWidth: 1,
        textStyle: { fontSize: 12, color: '#333' },
        formatter: (params: any[]) => {
          if (!params.length) return '';
          const time = dayjs(Number(params[0].axisValue) * 1000).format('YYYY-MM-DD HH:mm:ss');
          let html = `<div style="font-weight:500;margin-bottom:4px">${time}</div>`;

          const timeKey = String(params[0].axisValue);
          const detailForTime = details[timeKey];

          if (detailForTime && detailForTime.length > 0) {
            detailForTime.forEach((d: { label: string; value: string }) => {
              html += `<div style="display:flex;justify-content:space-between;gap:16px"><span>${d.label}</span><span style="font-weight:500">${d.value}</span></div>`;
            });
          } else {
            params.forEach((p: any, idx: number) => {
              const style = seriesStyles[idx] || {};
              const rawValue = Array.isArray(p.value) ? p.value[1] : p.value;
              if (rawValue == null) return;
              let displayValue: string;
              let displayUnit: string;
              if (needsBinaryScale) {
                const num = Number(rawValue);
                displayValue = num >= 100 ? num.toFixed(0) : num.toFixed(1);
                displayUnit = scaleDisplayUnit;
              } else {
                const seriesUnit = style.unit || unit;
                const formatted = formatMetricValue(Number(rawValue), seriesUnit as MetricUnit);
                displayValue = formatted.value;
                displayUnit = formatted.unit;
              }
              const color = style.color || CHART_COLORS[idx % CHART_COLORS.length];
              html += `<div style="display:flex;align-items:center;gap:6px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span><span>${displayValue} ${displayUnit}</span></div>`;
            });
          }
          return html;
        }
      },
      series: seriesList
    };
  }, [data, areaKeys, seriesStyles, unit, xAxisTimeFormat, leftAxisWidthOverride, details, gapIntervals]);

  const handleZrMouseDown = useCallback((params: any) => {
    if (!allowSelect || !onXRangeChange) return;
    dragStartRef.current = params.offsetX;
  }, [allowSelect, onXRangeChange]);

  const handleZrMouseUp = useCallback((params: any) => {
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
  }, [allowSelect, onXRangeChange, data]);

  const getInstanceRef = useRef<(() => any) | null>(null);

  const { containerRef, getInstance } = useECharts(option, {
    onEvents: allowSelect && onXRangeChange ? {
      mousedown: handleZrMouseDown,
      mouseup: handleZrMouseUp
    } : undefined
  });

  getInstanceRef.current = getInstance;

  const isEmpty = !data.length || !areaKeys.length;
  const showLoading = isEmpty && loading;

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {showLoading && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Spin size="small" />
        </div>
      )}
      {!showLoading && isEmpty && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  );
};

export default EChartsLineChart;
