'use client';

import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useECharts } from '../../../shared/widgets/useECharts';
import { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { CHART_COLORS } from '@/app/monitor/constants';
import { CardAlertDot, cardAlertClass } from './card-alert';
import { seriesMarkerColor } from './readings';
import type { TabAlertLevel } from './tab-level';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { describeFocusAxis, seriesSampleValues } from './focus-axis';
import { useProTimeWindow } from './pro-time-window';
import { useThemeColors } from './theme-color';
import ProDashLoading from './pro-dash-loading';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export interface ThinLegend {
  label: string;
  color: string;
  /** 悬停与折线 tooltip 用的完整名称。缺省时与 label 相同。 */
  title?: string;
  /** 图例项仍放不下时改用的更短文案。 */
  compactLabel?: string;
  /** 紧跟维度名的当前读数，例如「CPU 14.1%」「load1 0.88」。 */
  reading?: string;
  readingTone?: string;
  /** 参考线：虚线、略细，不盖过主序列。 */
  dashed?: boolean;
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
  /** 标题下的灰色副行。 */
  subtitle?: string;
  /** 标题右侧的附加操作，例如本机趋势磁盘图的「更多」。 */
  titleExtra?: React.ReactNode;
  className?: string;
  /** 嵌进已有卡片时不再套一层 panel。 */
  bare?: boolean;
  /**
   * 重点关注 spark：Y 轴只留数字，单位改到卡片标题右侧。
   * 实例趋势不要开。
   */
  numericAxis?: boolean;
  /** 每条序列一根 Y 轴。进程 CPU 可超过 100%，与内存共轴时会把内存压扁。 */
  independentAxes?: boolean;
  /**
   * 已不再打开图例。可见序列数等于 1 时整段图例不渲染，本开关和 reading 都不能把它打开。
   */
  showSeriesName?: boolean;
  /**
   * 双维卡即使只有一条线有采点，也保留全部图例名，并在 tooltip 里补上缺席的维度。
   * 单维卡不要开，避免主机盘把本该隐藏的图例重新打开。
   */
  keepLegend?: boolean;
  /** 本图达档。不传或 none 时不打点、不加框。 */
  alertLevel?: TabAlertLevel;
  onRetry?: () => void;
  /**
   * 单序列且窗口内只有一个数值时，不画左侧 Y 轴数字。
   * 刻度线还在。数值有起伏时仍显示刻度。
   */
  hideFlatAxisLabels?: boolean;
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

const isFlatSeries = (data: ChartData[], key: string) => {
  let seen: number | null = null;
  let count = 0;
  data.forEach((point) => {
    const value = point[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) return;
    count += 1;
    if (seen == null) {
      seen = value;
      return;
    }
    const scale = Math.max(Math.abs(seen), Math.abs(value), 1);
    if (Math.abs(value - seen) > scale * 1e-6) seen = Number.NaN;
  });
  return count > 0 && seen != null && Number.isFinite(seen);
};

const TICK_LADDER = [1, 2, 2.5, 5, 10];

const tidyAxis = (value: number) => (
  Number.isFinite(value) ? Number(value.toPrecision(12)) : 0
);

const niceStep = (span: number, maxTicks: number) => {
  const rough = span / Math.max(maxTicks - 1, 1);
  if (!(rough > 0)) return 1;
  const exp = Math.floor(Math.log10(rough));
  const base = 10 ** exp;
  const fraction = rough / base;
  const picked = TICK_LADDER.find((step) => step + 1e-9 >= fraction) ?? 10;
  return tidyAxis(picked * base);
};

const bumpStep = (step: number) => {
  const exp = Math.floor(Math.log10(step));
  const base = 10 ** exp;
  const fraction = step / base;
  const picked = TICK_LADDER.find((item) => item > fraction + 1e-6) ?? 10;
  return tidyAxis(picked * base);
};

/** 最多 4 个刻度。数据离 0 远时不把基线拉回 0，避免把一小段起伏拉成一条贴底的线。 */
const sparseAxisBounds = (values: number[]) => {
  if (!values.length) return null;
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (!(hi > lo)) {
    const pad = Math.abs(lo) > 0 ? Math.abs(lo) * 0.5 : 1;
    lo -= pad;
    hi += pad;
  }
  const span = hi - lo;
  if (lo > 0 && lo < span * 0.25) lo = 0;
  if (hi < 0 && Math.abs(hi) < span * 0.25) hi = 0;
  let interval = niceStep(hi - lo, 4);
  let min = tidyAxis(Math.floor(lo / interval) * interval);
  let max = tidyAxis(Math.ceil(hi / interval) * interval);
  let guard = 0;
  while (max > min && Math.round((max - min) / interval) + 1 > 4 && guard < 6) {
    interval = bumpStep(interval);
    min = tidyAxis(Math.floor(lo / interval) * interval);
    max = tidyAxis(Math.ceil(hi / interval) * interval);
    guard += 1;
  }
  if (!(max > min)) max = tidyAxis(min + interval);
  return { min, max, interval };
};

const seriesAxisValues = (data: ChartData[], key: string) => {
  const values: number[] = [];
  data.forEach((point) => {
    const value = point[key];
    if (typeof value === 'number' && Number.isFinite(value)) values.push(value);
  });
  return values;
};

/** 轴上把 70.00/s 收成 70/s。tooltip 仍走完整格式。 */
const compactTick = (value: number, unit: MetricUnit) => {
  const formatted = formatMetricValue(value, unit);
  const text = formatted.value
    .replace(/(\.\d*?[1-9])0+(?=\D|$)/g, '$1')
    .replace(/\.0+(?=\D|$)/g, '');
  return `${text}${formatted.unit || ''}`;
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
  subtitle,
  titleExtra,
  className,
  bare = false,
  numericAxis = false,
  independentAxes = false,
  keepLegend = false,
  alertLevel,
  onRetry,
  hideFlatAxisLabels = false
}: ThinTimeSeriesProps) {
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;
  const suspend = Boolean(proTime?.suspend);
  const plotted = useMemo(
    () => clipChartDataToWindow(data, chartWindow),
    [chartWindow, data]
  );
  const theme = useThemeColors();
  const axisColor = theme['--color-border'];
  const mutedColor = theme['--color-text-3'];
  const textColor = theme['--color-text-1'];
  const panelColor = theme['--color-bg'];
  const legendKey = legends.map((item) => `${item.label}\0${item.title || ''}\0${item.color}\0${item.reading || ''}\0${item.dashed ? '1' : '0'}`).join('\n');
  const legendBoxRef = useRef<HTMLDivElement>(null);
  const legendWidthRef = useRef(0);
  const [legendCompact, setLegendCompact] = useState(false);
  const [trackedLegendKey, setTrackedLegendKey] = useState(legendKey);
  if (trackedLegendKey !== legendKey) {
    setTrackedLegendKey(legendKey);
    setLegendCompact(false);
    legendWidthRef.current = 0;
  }
  useLayoutEffect(() => {
    const box = legendBoxRef.current;
    if (!box) return undefined;
    const canCompact = legends.some((item) => item.compactLabel && item.compactLabel !== item.label);
    if (!canCompact) return undefined;
    const measure = () => {
      const width = box.clientWidth;
      const grew = legendWidthRef.current > 0 && width > legendWidthRef.current + 8;
      legendWidthRef.current = width;
      if (grew) {
        setLegendCompact(false);
        return;
      }
      if (legendCompact) return;
      const clipped = Array.from(box.querySelectorAll<HTMLElement>('[data-legend-item]')).some(
        (node) => node.scrollWidth > node.clientWidth + 1
      );
      if (clipped) setLegendCompact(true);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [legendCompact, legendKey, legends]);
  const keys = useMemo(() => {
    const all = areaKeys(plotted);
    // 单图例只画一条线。value2 通常是同一指标的 or 回退，叠上去会双计。
    if (legends.length <= 1) return all.slice(0, 1);
    return all;
  }, [legends.length, plotted]);
  const seriesColors = useMemo(
    () => keys.map((_, index) => legends[index]?.color || CHART_COLORS[index % CHART_COLORS.length]),
    // legendKey 锁内容。legends 每次渲染都是新数组，放进依赖会让图在刷新时反复 setOption。
    [keys, legendKey]
  );
  const splitAxes = independentAxes && keys.length > 1;
  const option = useMemo(() => {
    if (suspend || !plotted.length || !keys.length) return null;
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
      if (timeSpan <= 36 * 3600) return stamp.format('HH:mm');
      return stamp.format('MM-DD');
    };
    const focusAxis = numericAxis
      ? describeFocusAxis(unit, seriesSampleValues(plotted))
      : null;
    const flatAxis = hideFlatAxisLabels && keys.length === 1 && isFlatSeries(plotted, keys[0]);
    const labeledAxis = !flatAxis && !focusAxis;
    const axisLabel = {
      fontSize: 10,
      margin: focusAxis?.labelMargin ?? 6,
      hideOverlap: true,
      formatter: (value: number) => {
        if (focusAxis) return focusAxis.formatTick(Number(value));
        return compactTick(Number(value), unit);
      }
    };
    const valueAxis = (samples: number[], color: string, showSplit: boolean) => {
      const bounds = focusAxis ? null : sparseAxisBounds(samples);
      return {
        type: 'value' as const,
        ...(bounds
          ? { min: bounds.min, max: bounds.max, interval: bounds.interval }
          : { splitNumber: 3 }),
        axisLabel: { ...axisLabel, color, show: !flatAxis },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: showSplit
          ? { lineStyle: { color: axisColor, width: 1 } }
          : { show: false }
      };
    };
    return {
      animation: false,
      backgroundColor: 'transparent',
      color: seriesColors,
      grid: {
        top: 8,
        right: labeledAxis ? 8 : (splitAxes ? 48 : 10),
        bottom: labeledAxis ? 4 : 28,
        left: flatAxis ? 8 : (focusAxis ? focusAxis.left : 4),
        containLabel: labeledAxis
      },
      xAxis: {
        type: 'value' as const,
        min: chartWindow ? chartWindow.startSec : 'dataMin' as const,
        max: chartWindow ? chartWindow.endSec : 'dataMax' as const,
        splitNumber: 3,
        axisLabel: {
          show: true,
          color: mutedColor,
          fontSize: 10,
          hideOverlap: true,
          showMinLabel: true,
          showMaxLabel: true,
          margin: 6,
          formatter: (value: number) => {
            const stamp = Number(value);
            const text = formatAxisTime(stamp);
            if (!text || !Number.isFinite(maxTime)) return text;
            // 窗口末端强制画出的刻度，和前一格落在同一分钟时会叠成两个 15:45。
            if (text === formatAxisTime(maxTime) && Math.abs(stamp - maxTime) > 1) return '';
            return text;
          }
        },
        axisTick: { show: true, length: 3, lineStyle: { color: axisColor } },
        axisLine: { lineStyle: { color: axisColor } },
        splitLine: { show: false }
      },
      yAxis: splitAxes
        ? keys.map((key, index) => ({
          ...valueAxis(seriesAxisValues(plotted, key), seriesColors[index] || mutedColor, index === 0),
          position: index === 0 ? 'left' as const : 'right' as const
        }))
        : valueAxis(
          keys.flatMap((key) => seriesAxisValues(plotted, key)),
          mutedColor,
          true
        ),
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
          const items = keepLegend
            ? keys.map((key, index) => {
              const name = legends[index]?.title || legends[index]?.label || key;
              const found = params.find((item) => item.seriesIndex === index)
                || params.find((item) => item.seriesName === name);
              return found || {
                seriesName: name,
                seriesIndex: index,
                color: legends[index]?.color,
                value: null
              };
            })
            : params;
          const rows = items
            .map((item) => {
              const raw = Array.isArray(item.value) ? item.value[1] : item.value;
              const name = item.seriesName || '';
              const color = seriesMarkerColor(legends, name, item.seriesIndex, item.color);
              return `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px"><span style="display:flex;align-items:center;gap:6px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span><span>${name}</span></span><span style="font-variant-numeric:tabular-nums;font-weight:600;color:${color}">${formatTooltipReading(raw, unit)}</span></div>`;
            })
            .join('');
          return `<div style="min-width:160px"><div style="margin-bottom:6px;color:var(--color-text-3)">${time}</div>${rows}</div>`;
        }
      },
      series: keys.map((key, index) => {
        const color = seriesColors[index];
        return {
          type: 'line' as const,
          name: legends[index]?.title || legends[index]?.label || key,
          ...(splitAxes ? { yAxisIndex: index } : {}),
          showSymbol: false,
          symbol: 'none' as const,
          smooth: 0.15,
          connectNulls: true,
          itemStyle: { color },
          data: plotted.map((point) => {
            const value = point[key];
            return [point.time, typeof value === 'number' ? value : null];
          }),
          lineStyle: {
            width: legends[index]?.dashed ? 1.2 : 1.6,
            color,
            type: legends[index]?.dashed ? 'dashed' as const : 'solid' as const
          }
        };
      })
    };
  }, [axisColor, chartWindow, hideFlatAxisLabels, keepLegend, keys, legendKey, mutedColor, numericAxis, panelColor, plotted, seriesColors, splitAxes, suspend, textColor, unit]);
  const { containerRef } = useECharts(option);
  const drawnSeriesCount = keys.filter((key) => plotted.some((point) => {
    const value = point[key];
    return typeof value === 'number' && Number.isFinite(value);
  })).length;
  const showLegend = keepLegend ? legends.length > 0 : drawnSeriesCount >= 2;
  const chart = (
    <>
      {title || reading || showLegend ? (
        <div className={styles.chartHead}>
          {title || reading ? (
            <div className={styles.chartTitleGroup}>
              {title ? (
                <div className={styles.chartTitleBlock}>
                  <div className={styles.chartTitle}>
                    {hint ? (
                      <span className="inline-flex items-center gap-1">
                        {title}
                        <Tooltip
                          title={hint.includes('\n') ? (
                            <div className="max-w-[360px] whitespace-pre-line text-[13px] font-normal leading-[1.55]">{hint}</div>
                          ) : hint}
                          styles={{ body: { maxWidth: 360 } }}
                        >
                          <QuestionCircleOutlined
                            className="cursor-help text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                            aria-label={hint}
                          />
                        </Tooltip>
                      </span>
                    ) : title}
                  </div>
                  {subtitle ? <div className={styles.chartSubtitle}>{subtitle}</div> : null}
                </div>
              ) : null}
              {titleExtra}
              {reading ? (
                <div className={styles.chartReading} style={readingTone ? { color: readingTone } : undefined}>
                  {reading}
                </div>
              ) : null}
            </div>
          ) : null}
          {showLegend ? (
            <div className={styles.chartLegend} ref={legendBoxRef}>
              {legends.map((item, index) => {
                const shown = legendCompact && item.compactLabel ? item.compactLabel : item.label;
                const hover = item.title || item.label;
                const chip = (
                  <span
                    key={`${hover}-${index}`}
                    className={styles.legendItem}
                    title={hover}
                    data-legend-item=""
                  >
                    <span
                      className={styles.legendSwatch}
                      style={item.dashed
                        ? {
                          width: 14,
                          height: 0,
                          borderRadius: 0,
                          borderTop: `1.5px dashed ${item.color}`,
                          background: 'transparent'
                        }
                        : { background: item.color }}
                    />
                    {shown}
                    {item.reading ? (
                      <span
                        className={styles.legendReading}
                        style={{ color: item.readingTone || item.color }}
                      >
                        {item.reading}
                      </span>
                    ) : null}
                  </span>
                );
                if (!item.title) return chip;
                return (
                  <Tooltip key={`${hover}-${index}`} title={hover}>
                    {chip}
                  </Tooltip>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className={styles.chartBody}>
        {suspend || !plotted.length ? (
          <div className={styles.chartEmpty}>
            {suspend || loading ? <ProDashLoading /> : (
              <span className="text-[13px] font-semibold text-[var(--color-text-2)]">{emptyText}</span>
            )}
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

  if (bare) return <div className={`min-w-0 ${className || ''}`}>{chart}</div>;
  return (
    <section className={`${classic.panel} ${styles.chartPanel} ${cardAlertClass(alertLevel)} ${className || ''}`}>
      <CardAlertDot level={alertLevel} />
      {chart}
    </section>
  );
}
