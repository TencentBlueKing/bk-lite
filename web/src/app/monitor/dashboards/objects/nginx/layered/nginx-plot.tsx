'use client';

import { useMemo } from 'react';
import dayjs from 'dayjs';
import { BarChart } from 'echarts/charts';
import echarts from '../../../shared/widgets/echarts-setup';
import { useECharts } from '../../../shared/widgets/useECharts';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { flatZeroStrokeSeries } from '../../host/layered/flat-zero-stroke';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { useThemeColors } from '../../host/layered/theme-color';
import { formatIntegerTick, integerCountAxis } from '../../../shared/widgets/integer-count-axis';
import { formatPlainTick, readableAxisBounds } from '../../host/layered/thin-time-series';
import { chartRows, type NginxSeriesItem } from './model';

echarts.use([BarChart]);

const seriesKey = (index: number) => `value${String(index + 1).padStart(2, '0')}`;

const readValue = (row: { time: number; [key: string]: unknown }, key: string) => {
  const value = row[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

export function NginxPlot({
  items,
  kind,
  floor,
  percent,
  formatReading,
  height,
  countAxis = false
}: {
  items: readonly NginxSeriesItem[];
  kind: 'line' | 'step' | 'bar';
  floor: number;
  percent: boolean;
  formatReading: (value: number) => string;
  height: number;
  /** 计数类纵轴只出整数刻度。速率、耗时、字节不走这条。 */
  countAxis?: boolean;
}) {
  const proTime = useProTimeWindow();
  const theme = useThemeColors();
  const chartWindow = proTime?.window ?? null;
  const suspend = Boolean(proTime?.suspend);
  const rows = useMemo(() => chartRows(items), [items]);
  const plotted = useMemo(
    () => clipChartDataToWindow(rows, chartWindow),
    [chartWindow, rows]
  );
  const keys = useMemo(() => items.map((_, index) => seriesKey(index)), [items]);
  const option = useMemo(() => {
    if (suspend || !plotted.length || !keys.length) return null;
    const axisColor = theme['--color-border'] || '#d9d9d9';
    const mutedColor = theme['--color-text-3'] || '#8c8c8c';
    const textColor = theme['--color-text-1'] || '#1f1f1f';
    const panelColor = theme['--color-bg'] || '#ffffff';
    let minTime = chartWindow?.startSec ?? Number.POSITIVE_INFINITY;
    let maxTime = chartWindow?.endSec ?? Number.NEGATIVE_INFINITY;
    if (!chartWindow) {
      plotted.forEach((point) => {
        const time = Number(point.time);
        if (!Number.isFinite(time)) return;
        if (time < minTime) minTime = time;
        if (time > maxTime) maxTime = time;
      });
    }
    const timeSpan = Number.isFinite(minTime) && Number.isFinite(maxTime) ? maxTime - minTime : 0;
    const formatAxisTime = (value: number) => {
      const stamp = dayjs(value * 1000);
      if (!stamp.isValid()) return '';
      return timeSpan <= 36 * 3600 ? stamp.format('HH:mm') : stamp.format('MM-DD');
    };
    const samples = plotted.flatMap((point) => keys.flatMap((key) => {
      const value = readValue(point, key);
      return value == null ? [] : [value];
    }));
    const stacked = kind === 'bar'
      ? plotted.map((point) => keys.reduce((sum, key) => sum + (readValue(point, key) ?? 0), 0))
      : samples;
    const countBounds = countAxis ? integerCountAxis(stacked.length ? stacked : [0]) : null;
    const seeded = [...(samples.length ? samples : [0]), ...(floor > 0 ? [floor] : [])];
    const sharedBounds = readableAxisBounds(seeded, 'none', true);
    const bounds = percent
      ? { min: 0, max: 100, interval: 50 }
      : countBounds ?? sharedBounds ?? { min: 0, max: 1, interval: 1 };
    const mark = plotted.length <= 30;
    return {
      animation: false,
      backgroundColor: 'transparent',
      grid: { top: 8, right: 12, bottom: 28, left: 8, containLabel: true },
      xAxis: {
        type: 'value' as const,
        min: chartWindow ? chartWindow.startSec : 'dataMin' as const,
        max: chartWindow ? chartWindow.endSec : 'dataMax' as const,
        axisLabel: {
          color: mutedColor,
          fontSize: 10,
          hideOverlap: true,
          formatter: (value: number) => formatAxisTime(value)
        },
        axisTick: { show: true, length: 3, lineStyle: { color: axisColor } },
        axisLine: { lineStyle: { color: axisColor } },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value' as const,
        min: bounds.min,
        max: bounds.max,
        interval: bounds.interval,
        ...(countBounds ? { minInterval: 1 } : {}),
        axisLabel: {
          color: mutedColor,
          fontSize: 10,
          formatter: (value: number) => (
            countBounds ? formatIntegerTick(value) : formatPlainTick(value)
          )
        },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: axisColor, width: 1 } }
      },
      tooltip: {
        show: true,
        trigger: 'axis' as const,
        appendToBody: false,
        confine: true,
        backgroundColor: panelColor,
        borderColor: axisColor,
        borderWidth: 1,
        textStyle: { fontSize: 12, color: textColor },
        formatter: (params: any[]) => {
          if (!Array.isArray(params) || !params.length) return '';
          const time = dayjs(Number(params[0].axisValue) * 1000).format('YYYY-MM-DD HH:mm:ss');
          const rowsHtml = keys.map((key, index) => {
            const name = items[index]?.label || key;
            const color = items[index]?.color || '#2f6bff';
            const raw = readValue(plotted.find((point) => point.time === Number(params[0].axisValue)) || { time: 0 }, key);
            const readingText = raw == null ? '--' : formatReading(raw);
            return `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px"><span style="display:flex;align-items:center;gap:6px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span><span>${name}</span></span><span style="font-variant-numeric:tabular-nums;font-weight:600;color:${color}">${readingText}</span></div>`;
          }).join('');
          return `<div style="min-width:160px"><div style="margin-bottom:6px;color:${mutedColor}">${time}</div>${rowsHtml}</div>`;
        }
      },
      series: keys.map((key, index) => {
        const item = items[index];
        const color = item?.color || '#2f6bff';
        const name = item?.label || key;
        const values = plotted.map((point) => readValue(point, key));
        const finite = values.filter((value): value is number => value != null);
        const allZero = finite.length > 0 && finite.every((value) => value === 0);
        if (kind !== 'bar' && allZero) {
          return flatZeroStrokeSeries({
            name,
            color,
            liftPx: 8,
            symbols: mark,
            symbolRadius: 2,
            breakOnNull: true,
            points: plotted.map((point) => [Number(point.time), readValue(point, key)] as const)
          });
        }
        if (kind === 'bar') {
          return {
            type: 'bar' as const,
            name,
            stack: 'nginx-stack',
            barWidth: '60%',
            itemStyle: { color },
            data: plotted.map((point) => [point.time, readValue(point, key)])
          };
        }
        return {
          type: 'line' as const,
          name,
          step: kind === 'step' ? 'end' as const : undefined,
          smooth: kind === 'step' ? 0 : 0.15,
          connectNulls: false,
          showSymbol: mark,
          symbol: mark ? 'circle' as const : 'none' as const,
          symbolSize: 4,
          itemStyle: { color },
          lineStyle: { width: 1.6, color },
          data: plotted.map((point) => [point.time, readValue(point, key)])
        };
      })
    };
  }, [chartWindow, countAxis, floor, formatReading, items, keys, kind, percent, plotted, suspend, theme]);
  const { containerRef } = useECharts(option);
  return <div ref={containerRef} className="h-full w-full" style={{ height }} />;
}
