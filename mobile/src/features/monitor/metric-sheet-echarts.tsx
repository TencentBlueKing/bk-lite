'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsType } from 'echarts/core';
import type { EChartsOption } from 'echarts';
import type { DateTimePreferences } from '@/platform/preferences/dateTime';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import { formatMetricDisplay, metricTimestampMs } from './metric-chart-utils';
import type { metricSeriesPoints } from './model';
import styles from './monitor.module.css';

type SeriesList = ReturnType<typeof metricSeriesPoints>;
type EchartsCore = typeof import('./echarts-setup').default;
interface TooltipFormatterParams {
  value?: number | string | (number | string)[];
  axisValue?: number | string;
  color?: string;
}

function formatTooltip(
  params: unknown,
  preferences: DateTimePreferences,
  tooltipTimeOpts: Intl.DateTimeFormatOptions,
  unit: string,
  primary: string,
) {
  const rows = (Array.isArray(params) ? params : [params]) as TooltipFormatterParams[];
  const first = rows[0];
  if (!first) return '';
  const axisValue = Array.isArray(first.value) ? Number(first.value[0]) : Number(first.axisValue);
  const time = formatAccountDateTime(axisValue, preferences, tooltipTimeOpts);
  const lines = rows.flatMap((row, index) => {
    const raw = Array.isArray(row.value) ? row.value[1] : row.value;
    if (raw == null || Number.isNaN(Number(raw))) return [];
    const label = formatMetricDisplay(Number(raw), unit);
    const color = typeof row.color === 'string' ? row.color : primary;
    return [
      `<div style="display:flex;align-items:center;gap:6px;margin-top:4px">`
      + `<span style="width:8px;height:8px;border-radius:50%;background:${color}"></span>`
      + `<span>${rows.length > 1 ? `${index + 1}: ` : ''}${label}</span>`
      + `</div>`,
    ];
  });
  return `<div style="font-weight:600;margin-bottom:2px">${time}</div>${lines.join('')}`;
}

function cssVar(name: string, fallback: string) {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function withAlpha(color: string, alphaHex: string) {
  if (/^#[0-9a-fA-F]{6}$/.test(color)) return `${color}${alphaHex}`;
  if (/^#[0-9a-fA-F]{3}$/.test(color)) {
    const [r = '0', g = '0', b = '0'] = color.slice(1);
    return `#${r}${r}${g}${g}${b}${b}${alphaHex}`;
  }
  return null;
}

function axisTimeOptions(rangeMinutes: number): Intl.DateTimeFormatOptions {
  if (rangeMinutes >= 1440) {
    return { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' };
  }
  if (rangeMinutes <= 60) {
    return { hour: '2-digit', minute: '2-digit', second: '2-digit' };
  }
  return { hour: '2-digit', minute: '2-digit' };
}

interface Props {
  series: SeriesList;
  unit: string;
  rangeMinutes: number;
  preferences: DateTimePreferences;
}

export default function MetricSheetEcharts({
  series,
  unit,
  rangeMinutes,
  preferences,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<EChartsType | null>(null);
  const [echartsMod, setEchartsMod] = useState<EchartsCore | null>(null);

  useEffect(() => {
    let cancelled = false;
    void import('./echarts-setup').then((mod) => {
      if (!cancelled) setEchartsMod(mod.default);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const option = useMemo((): EChartsOption | null => {
    const prepared = series
      .map((item) => item.points
        .map(([timestamp, value]) => [metricTimestampMs(timestamp), value] as const)
        .filter((point) => Number.isFinite(point[0]) && Number.isFinite(point[1])))
      .filter((points) => points.length > 0);
    if (!prepared.length) return null;

    const text3 = cssVar('--color-text-3', '#86909c');
    const text2 = cssVar('--color-text-2', '#4e5969');
    const border = cssVar('--color-border-1', '#e5e6eb');
    const primary = cssVar('--color-primary', '#165dff');
    const bg = cssVar('--color-bg', '#ffffff');
    const timeOpts = axisTimeOptions(rangeMinutes);
    const tooltipTimeOpts: Intl.DateTimeFormatOptions = {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    };
    const allZero = prepared.every((points) => points.every((point) => point[1] === 0));
    const areaTop = withAlpha(primary, '33');
    const areaBottom = withAlpha(primary, '05');

    return {
      animationDuration: 220,
      grid: {
        left: 2,
        right: 6,
        top: 10,
        bottom: 2,
        containLabel: true,
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'mousemove|click|mousewheel',
        confine: true,
        backgroundColor: bg,
        borderColor: border,
        borderWidth: 1,
        textStyle: { color: text2, fontSize: 12 },
        axisPointer: {
          type: 'line',
          snap: true,
          lineStyle: { color: text3, type: 'dashed', width: 1 },
        },
        formatter: (params) => formatTooltip(params, preferences, tooltipTimeOpts, unit, primary),
      },
      xAxis: {
        type: 'time',
        axisLabel: {
          color: text3,
          fontSize: 10,
          hideOverlap: true,
          formatter: (value: number) => formatAccountDateTime(value, preferences, timeOpts),
        },
        axisLine: { lineStyle: { color: border } },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        min: allZero ? 0 : undefined,
        max: allZero ? 1 : undefined,
        scale: !allZero,
        splitNumber: 3,
        axisLabel: {
          color: text3,
          fontSize: 10,
          formatter: (value: number) => (
            allZero && value !== 0 ? '' : formatMetricDisplay(value, unit)
          ),
        },
        splitLine: { lineStyle: { color: border, type: 'dashed' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: prepared.map((points, index) => ({
        type: 'line' as const,
        showSymbol: false,
        smooth: false,
        connectNulls: true,
        data: points.map(([time, value]) => [time, value]),
        lineStyle: {
          width: 2,
          color: primary,
          opacity: Math.max(0.45, 1 - index * 0.18),
        },
        itemStyle: { color: primary },
        areaStyle: index === 0 && areaTop && areaBottom ? {
          color: {
            type: 'linear' as const,
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: areaTop },
              { offset: 1, color: areaBottom },
            ],
          },
        } : undefined,
      })),
    } satisfies EChartsOption;
  }, [preferences, rangeMinutes, series, unit]);

  useEffect(() => {
    const node = containerRef.current;
    if (!echartsMod || !node) return;

    const instance = echartsMod.init(node);
    instanceRef.current = instance;
    const resizeObserver = new ResizeObserver(() => instance.resize());
    resizeObserver.observe(node);

    return () => {
      resizeObserver.disconnect();
      instance.dispose();
      instanceRef.current = null;
    };
  }, [echartsMod]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !echartsMod) return;
    if (!option) {
      instance.clear();
      return;
    }
    instance.setOption(option, { notMerge: true });
    const frameId = requestAnimationFrame(() => instance.resize());
    return () => cancelAnimationFrame(frameId);
  }, [option, echartsMod]);

  return <div ref={containerRef} className={styles.metricSheetChart} role="img" />;
}
