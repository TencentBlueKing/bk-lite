'use client';

import React, { useMemo, useCallback, useRef } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { Empty } from 'antd';
import { ChartData, MetricItem } from '@/app/monitor/types';
import { useECharts } from './useECharts';
import { formatMetricValue } from '../utils/format';
import { MetricUnit } from '../types';

export interface EChartsLineChartProps {
  data: ChartData[];
  unit?: string;
  metric?: MetricItem;
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
  '#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452',
  '#6DC8EC', '#945FB9', '#FF9845', '#1E9493'
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

const EChartsLineChart: React.FC<EChartsLineChartProps> = ({
  data,
  unit = '',
  seriesStyles = [],
  xAxisTimeFormat = 'HH:mm',
  leftAxisWidthOverride,
  allowSelect = true,
  onXRangeChange
}) => {
  const dragStartRef = useRef<number | null>(null);

  const areaKeys = useMemo(() => getChartAreaKeys(data), [data]);

  const details = useMemo(() => {
    return data.reduce<Record<string, Array<{ name: string; label: string; value: string }>>>((pre, cur) => {
      return Object.assign(pre, cur.details);
    }, {});
  }, [data]);

  const option = useMemo(() => {
    if (!data.length || !areaKeys.length) return null;

    const times = data.map((d) => d.time);
    const seriesList = areaKeys.map((key, idx) => {
      const style = seriesStyles[idx] || {};
      const color = style.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
      const fillOpacity = style.fillOpacity ?? 0.05;
      const strokeOpacity = style.strokeOpacity ?? 1;
      const strokeWidth = style.strokeWidth ?? 2;
      const isDashed = !!style.strokeDasharray;

      return {
        type: 'line' as const,
        name: key,
        data: data.map((d) => (d[key] as number) ?? null),
        smooth: false,
        symbol: 'none',
        lineStyle: {
          width: strokeWidth,
          color,
          opacity: strokeOpacity,
          type: isDashed ? ('dashed' as const) : ('solid' as const)
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
        emphasis: { disabled: true }
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
        type: 'category' as const,
        data: times,
        axisLabel: {
          formatter: (val: string) => dayjs(Number(val) * 1000).format(xAxisTimeFormat),
          fontSize: 11,
          color: '#8c8c8c'
        },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value' as const,
        axisLabel: {
          formatter: (val: number) => formatAxisNumber(val),
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
              const seriesUnit = style.unit || unit;
              const rawValue = p.value;
              if (rawValue == null) return;
              const formatted = formatMetricValue(Number(rawValue), seriesUnit as MetricUnit);
              const color = style.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
              html += `<div style="display:flex;align-items:center;gap:6px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span><span>${formatted.value} ${formatted.unit}</span></div>`;
            });
          }
          return html;
        }
      },
      series: seriesList
    };
  }, [data, areaKeys, seriesStyles, unit, xAxisTimeFormat, leftAxisWidthOverride, details]);

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
      const times = data.map((d) => d.time);
      const startIdx = Math.max(0, Math.min(Math.round(xAxis[0]), times.length - 1));
      const endIdx = Math.max(0, Math.min(Math.round(xAxisEnd[0]), times.length - 1));
      const startTime = dayjs(times[startIdx] * 1000);
      const endTime = dayjs(times[endIdx] * 1000);
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

  if (!data.length || !areaKeys.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '20px 0' }} />;
  }

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
};

export default EChartsLineChart;
