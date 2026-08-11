'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsType } from 'echarts/core';
import type { EChartsOption } from 'echarts';
import type { DateTimePreferences } from '@/platform/preferences/dateTime';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import {
  attachGapIntervals,
  GAP_BOUNDARY_COLOR,
  GAP_FILL_COLOR,
  getChartDataWithGapBreaks,
  getRenderedGapIntervals,
  type GapInterval,
} from './gap-intervals';
import {
  buildMetricNiceAxis,
  buildMetricYAxisDomain,
  formatMetricAxisNumber,
  formatMetricDisplay,
  metricAxisTimeOptions,
  metricTimestampMs,
} from './metric-chart-utils';
import {
  chartDataToMetricSeries,
  metricSeriesToChartData,
  metricTimestampSeconds,
  type metricSeriesPoints,
} from './model';
import styles from './monitor.module.css';

type SeriesList = ReturnType<typeof metricSeriesPoints>;
type EchartsCore = typeof import('./echarts-setup').default;
interface TooltipFormatterParams {
  value?: number | string | (number | string)[];
  axisValue?: number | string;
  color?: string;
}

/** 与 web 详情图高度 ≤220 时 tickCount=3 对齐（mobile sheet 图约 180px）。 */
const Y_AXIS_TICK_COUNT = 3;

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

interface Props {
  series: SeriesList;
  gaps: GapInterval[];
  unit: string;
  /** 与 query_range 一致的完整时间窗（毫秒）。 */
  startMs: number;
  endMs: number;
  preferences: DateTimePreferences;
}

export default function MetricSheetEcharts({
  series,
  gaps,
  unit,
  startMs,
  endMs,
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
    if (!series.length) return null;

    const xAxisDomainSec: [number, number] = [
      metricTimestampSeconds(startMs),
      metricTimestampSeconds(endMs),
    ];
    const chartData = metricSeriesToChartData(series);
    const withGaps = attachGapIntervals(chartData, gaps);
    const broken = getChartDataWithGapBreaks(withGaps, gaps, xAxisDomainSec);
    const prepared = chartDataToMetricSeries(broken, series)
      .map((item) => item.points
        .map(([timestamp, value]) => [metricTimestampMs(timestamp), value] as const)
        .filter((point) => Number.isFinite(point[0])))
      .filter((points) => points.some((point) => point[1] !== null));
    if (!prepared.length) return null;

    const renderedGaps = getRenderedGapIntervals(withGaps, gaps, xAxisDomainSec)
      .filter((gap) => gap.end > gap.start)
      .map((gap) => ({
        startMs: metricTimestampMs(gap.start),
        endMs: metricTimestampMs(gap.end),
      }));

    const text3 = cssVar('--color-text-3', '#86909c');
    const text2 = cssVar('--color-text-2', '#4e5969');
    const border = cssVar('--color-border-1', '#e5e6eb');
    const primary = cssVar('--color-primary', '#165dff');
    const bg = cssVar('--color-bg', '#ffffff');
    const tooltipTimeOpts: Intl.DateTimeFormatOptions = {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    };

    const values = prepared.flatMap((points) => (
      points.flatMap((point) => (point[1] === null ? [] : [point[1]]))
    ));
    // X 轴按所选时间窗定域，标签格式按完整窗跨度分档（对齐 Web useFormatTime）。
    const axisSpanMs = Math.max(endMs - startMs, 0);
    const timeOpts = metricAxisTimeOptions(axisSpanMs);

    const allZero = values.length > 0 && values.every((value) => value === 0);
    const niceYAxis = buildMetricNiceAxis(
      allZero ? [0, 1] : buildMetricYAxisDomain(values),
      Y_AXIS_TICK_COUNT,
    );
    const areaTop = withAlpha(primary, '33');
    const areaBottom = withAlpha(primary, '05');
    const gapBoundaryTimes = Array.from(new Set(
      renderedGaps
        .flatMap((gap) => [gap.startMs, gap.endMs])
        .filter((time) => time > startMs && time < endMs),
    ));

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
        min: startMs,
        max: endMs,
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
        min: niceYAxis.domain[0],
        max: niceYAxis.domain[1],
        interval: niceYAxis.interval,
        scale: false,
        axisLabel: {
          color: text3,
          fontSize: 10,
          formatter: (value: number) => (
            allZero && value !== 0 ? '' : formatMetricAxisNumber(value)
          ),
        },
        splitLine: { lineStyle: { color: border, type: 'dashed' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: prepared.map((points, index) => ({
        type: 'line' as const,
        // 对齐 Web Area `dot={false}`：常显 symbol 关闭，连续段画线，缺口处靠 null 断线。
        showSymbol: false,
        symbol: 'none',
        clip: true,
        smooth: false,
        connectNulls: false,
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
        markArea: index === 0 && renderedGaps.length ? {
          silent: true,
          itemStyle: {
            color: GAP_FILL_COLOR,
            borderWidth: 0,
          },
          data: renderedGaps.map((gap) => [
            { xAxis: gap.startMs },
            { xAxis: gap.endMs },
          ]),
        } : undefined,
        markLine: index === 0 && gapBoundaryTimes.length ? {
          silent: true,
          symbol: 'none',
          lineStyle: {
            color: GAP_BOUNDARY_COLOR,
            type: 'dashed',
            width: 1,
          },
          label: { show: false },
          data: gapBoundaryTimes.map((time) => ({ xAxis: time })),
        } : undefined,
      })),
    } satisfies EChartsOption;
  }, [endMs, gaps, preferences, series, startMs, unit]);

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
