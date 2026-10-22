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
  subtitle,
  titleExtra,
  className,
  bare = false,
  numericAxis = false,
  independentAxes = false,
  keepLegend = false,
  alertLevel,
  onRetry
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
    const axisLabel = {
      fontSize: 10,
      margin: focusAxis?.labelMargin ?? 8,
      formatter: (value: number) => {
        if (focusAxis) return focusAxis.formatTick(Number(value));
        const formatted = formatMetricValue(value, unit);
        return `${formatted.value}${formatted.unit || ''}`;
      }
    };
    return {
      animation: false,
      backgroundColor: 'transparent',
      color: seriesColors,
      grid: {
        top: 8,
        right: splitAxes ? 48 : 10,
        bottom: 28,
        left: focusAxis ? focusAxis.left : 44,
        containLabel: false
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
          margin: 6,
          formatter: (value: number) => formatAxisTime(Number(value))
        },
        axisTick: { show: true, length: 3, lineStyle: { color: axisColor } },
        axisLine: { lineStyle: { color: axisColor } },
        splitLine: { show: false }
      },
      yAxis: splitAxes
        ? keys.map((_, index) => ({
          type: 'value' as const,
          position: index === 0 ? 'left' as const : 'right' as const,
          axisLabel: { ...axisLabel, color: seriesColors[index] || mutedColor },
          axisTick: { show: false },
          axisLine: { show: false },
          splitLine: index === 0
            ? { lineStyle: { color: axisColor, width: 1 } }
            : { show: false }
        }))
        : {
          type: 'value' as const,
          axisLabel: { ...axisLabel, color: mutedColor },
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
  }, [axisColor, chartWindow, keepLegend, keys, legendKey, mutedColor, numericAxis, panelColor, plotted, seriesColors, splitAxes, suspend, textColor, unit]);
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
                        <Tooltip title={hint} styles={{ body: { maxWidth: 360 } }}>
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
