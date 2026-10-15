'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { hostCategoryText } from './category-copy';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../config';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import { CardAlertDot, cardAlertClass } from './card-alert';
import ThinTimeSeries from './thin-time-series';
import type { HostSurfaceAlerts } from './tab-level';
import { metricBlockPhase, type MetricBlockPhase } from './performance-scope';
import {
  deriveRatioPercent,
  formatPlain,
  latestNumber,
  metricHasPoints,
  numericValue,
  primaryChartSeries,
  resolveMemoryUsage
} from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const CPU_BREAKDOWN = [
  { key: 'cpu_usage_user_total', label: 'user', color: HOST_PALETTE.emerald },
  { key: 'cpu_usage_system_total', label: 'system', color: HOST_PALETTE.neutral },
  { key: 'cpu_usage_iowait_total', label: 'iowait', color: HOST_PALETTE.orange },
  { key: 'cpu_usage_irq_total', label: 'irq', color: HOST_PALETTE.indigo },
  { key: 'cpu_usage_steal_total', label: 'steal', color: HOST_PALETTE.rose }
];

const LOAD_SERIES = [
  { key: 'system_load1', label: 'load1', color: HOST_SERIES_COLOR.load1 },
  { key: 'system_load5', label: 'load5', color: HOST_SERIES_COLOR.load5 },
  { key: 'system_load15', label: 'load15', color: HOST_SERIES_COLOR.load15 }
];

/** 性能 KPI 主值跟本页对应折线，并与概览、进程共用同一 token。 */
const CPU_SERIES_COLOR = HOST_SERIES_COLOR.cpu;
const MEM_USED_COLOR = HOST_SERIES_COLOR.memUsed;
const LOAD1_SERIES_COLOR = HOST_SERIES_COLOR.load1;

const MEM_COMPOSITION = [
  { key: 'mem_used', label: 'used', color: HOST_SERIES_COLOR.memUsed },
  { key: 'mem_cached', label: 'cached', color: HOST_PALETTE.emerald },
  { key: 'mem_buffered', label: 'buffered', color: HOST_PALETTE.cyan },
  { key: 'mem_shared', label: 'shared', color: HOST_PALETTE.indigo }
] as const;

const GPU_SERIES = [
  { key: 'nvidia_smi_utilization_gpu', title: 'GPU 使用率', unit: 'percent' as const },
  { key: 'nvidia_smi_utilization_memory', title: 'GPU 显存', unit: 'percent' as const },
  { key: 'nvidia_smi_temperature_gpu', title: 'GPU 温度', unit: 'celsius' as const }
] as const;

const SWAP_SERIES_COLOR = HOST_PALETTE.emerald;

/** 同一时间点 total - part。对不齐的点丢掉。 */
const subtractAligned = (
  total: MetricSeries['viewData'] | undefined,
  part: MetricSeries['viewData'] | undefined
) => {
  if (!total?.length || !part?.length) return [];
  const parts = new Map<number, number>();
  part.forEach((point) => {
    const time = Number(point.time);
    const value = numericValue(point);
    if (Number.isFinite(time) && value != null) parts.set(time, value);
  });
  const result: ChartData[] = [];
  total.forEach((point) => {
    const time = Number(point.time);
    const base = numericValue(point);
    const sub = parts.get(time);
    if (!Number.isFinite(time) || base == null || sub == null) return;
    result.push({ time, value1: Math.max(0, base - sub) });
  });
  return result;
};

const splitMetric = (value: number | null, unit: MetricUnit) => {
  if (value == null) return { value: '--', unit: '' };
  const formatted = formatMetricValue(value, unit);
  return { value: formatted.value, unit: formatted.unit };
};

const EMPTY_PENDING: ReadonlySet<string> = new Set();

const loadStateOf = (
  metrics: Record<string, MetricSeries | undefined>,
  names: readonly string[]
) => {
  const states: Record<string, 'success' | 'error' | undefined> = {};
  names.forEach((name) => {
    const state = metrics[name]?.loadState;
    if (state === 'success' || state === 'error') states[name] = state;
  });
  return states;
};

const latestSeriesValue = (series: ChartData[]) => {
  for (let index = series.length - 1; index >= 0; index -= 1) {
    const value = numericValue(series[index]);
    if (value != null) return value;
  }
  return null;
};

const formatBytes = (value: number) => {
  const formatted = formatMetricValue(value, 'bytes');
  return `${formatted.value}${formatted.unit || ''}`;
};

export default function SystemPane({
  metrics,
  pendingMetricNames = EMPTY_PENDING,
  onRetryMetrics,
  alerts
}: {
  metrics: Record<string, MetricSeries | undefined>;
  pendingMetricNames?: ReadonlySet<string>;
  onRetryMetrics?: (names: string[]) => void;
  alerts: HostSurfaceAlerts['system'];
}) {
  const { t } = useDashboardText();

  const breakdown = CPU_BREAKDOWN.filter((item) => metricHasPoints(metrics[item.key]));
  const loadItems = LOAD_SERIES.filter((item) => metricHasPoints(metrics[item.key]));
  const loadTrend = useMemo(() => {
    const items = LOAD_SERIES.filter((item) => metricHasPoints(metrics[item.key]));
    if (!items.length) return [];
    return mergeChartSeries(items.map((item) => ({
      key: item.key,
      label: item.label,
      data: primaryChartSeries(metrics[item.key]?.viewData)
    })));
  }, [
    metrics.system_load1?.viewData,
    metrics.system_load1?.loadState,
    metrics.system_load5?.viewData,
    metrics.system_load5?.loadState,
    metrics.system_load15?.viewData,
    metrics.system_load15?.loadState
  ]);
  const breakdownTrend = useMemo(() => {
    const items = CPU_BREAKDOWN.filter((item) => metricHasPoints(metrics[item.key]));
    if (!items.length) return [];
    return mergeChartSeries(items.map((item) => ({
      key: item.key,
      label: item.label,
      data: primaryChartSeries(metrics[item.key]?.viewData)
    })));
  }, [
    metrics.cpu_usage_user_total?.viewData,
    metrics.cpu_usage_user_total?.loadState,
    metrics.cpu_usage_system_total?.viewData,
    metrics.cpu_usage_system_total?.loadState,
    metrics.cpu_usage_iowait_total?.viewData,
    metrics.cpu_usage_iowait_total?.loadState,
    metrics.cpu_usage_irq_total?.viewData,
    metrics.cpu_usage_irq_total?.loadState,
    metrics.cpu_usage_steal_total?.viewData,
    metrics.cpu_usage_steal_total?.loadState
  ]);
  const memoryUsage = useMemo(
    () => resolveMemoryUsage(
      metrics.mem_available?.viewData,
      metrics.mem_total?.viewData,
      metrics.mem_used_percent
    ),
    [
      metrics.mem_available?.viewData,
      metrics.mem_total?.viewData,
      metrics.mem_used_percent?.viewData,
      metrics.mem_used_percent?.loadState
    ]
  );
  const cpuTrend = useMemo(
    () => primaryChartSeries(metrics.cpu_usage_total?.viewData),
    [metrics.cpu_usage_total?.viewData]
  );
  // 有总量时已用/可用按 available 互补，避免 mem_used_percent 与 MemAvailable 叠成超过 100%。
  // 缺总量时只画采集到的使用率，不造第二条百分比。
  const memChart = useMemo(() => {
    const items = [
      ...(memoryUsage.used.length
        ? [{ key: 'used', label: '已用', color: MEM_USED_COLOR, data: memoryUsage.used }]
        : []),
      ...(memoryUsage.available.length
        ? [{ key: 'available', label: '可用', color: HOST_SERIES_COLOR.memAvailable, data: memoryUsage.available }]
        : [])
    ];
    const data = items.length
      ? mergeChartSeries(items.map((item) => ({ key: item.key, label: item.label, data: item.data })))
      : [];
    return { items, data };
  }, [memoryUsage]);
  const memItems = memChart.items;
  const cpuNow = latestNumber(metrics.cpu_usage_total);
  // 曲线已用是 available/total 的互补占比。内存使用率 KPI 跟这条线。
  const memNow = memoryUsage.usedNow;
  // 可用内存卡显示容量，不显示占比。
  const availBytes = latestNumber(metrics.mem_available);
  const uptimeNow = latestNumber(metrics.system_uptime);
  const load1Now = latestNumber(metrics.system_load1);
  const phaseFor = (names: readonly string[], hasValue: boolean): MetricBlockPhase => (
    metricBlockPhase(names, pendingMetricNames, loadStateOf(metrics, names), hasValue)
  );
  const retry = (names: readonly string[]) => () => onRetryMetrics?.([...names]);
  const cpuNames = ['cpu_usage_total'] as const;
  const memKpiNames = ['mem_used_percent'] as const;
  const availNames = ['mem_available'] as const;
  const load1Names = ['system_load1'] as const;
  const uptimeNames = ['system_uptime'] as const;
  const memTrendNames = ['mem_used_percent', 'mem_available', 'mem_total'] as const;
  const loadNames = LOAD_SERIES.map((item) => item.key);
  const breakdownNames = CPU_BREAKDOWN.map((item) => item.key);
  const loadActive = loadNames.some((name) => pendingMetricNames.has(name) || metrics[name]);
  const cpuPhase = phaseFor(cpuNames, metricHasPoints(metrics.cpu_usage_total));
  const memPhase = phaseFor(memTrendNames, memItems.length > 0);
  const loadPhase = phaseFor(loadNames, loadItems.length > 0);
  const breakdownPhase = phaseFor(breakdownNames, breakdown.length > 0);
  const instantCards: Array<{
    key: string;
    label: string;
    value: string;
    unit: string;
    names: readonly string[];
    phase: MetricBlockPhase;
    valueColor?: string;
    alertLevel?: HostSurfaceAlerts['system']['cpu'];
  }> = [
    {
      key: 'cpu',
      label: 'CPU',
      names: cpuNames,
      phase: phaseFor(cpuNames, cpuNow != null),
      valueColor: CPU_SERIES_COLOR,
      alertLevel: alerts.cpu,
      ...splitMetric(cpuNow, 'percent')
    },
    {
      key: 'mem',
      label: '内存',
      names: memoryUsage.complementary ? memTrendNames : memKpiNames,
      phase: phaseFor(memoryUsage.complementary ? memTrendNames : memKpiNames, memNow != null),
      valueColor: MEM_USED_COLOR,
      alertLevel: alerts.mem,
      ...splitMetric(memNow, 'percent')
    },
    { key: 'avail', label: '可用内存', names: availNames, phase: phaseFor(availNames, availBytes != null), ...splitMetric(availBytes, 'bytes') },
    {
      key: 'load',
      label: hostCategoryText(t, 'loadOneMinute'),
      names: load1Names,
      phase: phaseFor(load1Names, load1Now != null),
      value: formatPlain(load1Now),
      unit: '',
      valueColor: LOAD1_SERIES_COLOR,
      alertLevel: alerts.load
    },
    {
      key: 'uptime',
      label: hostCategoryText(t, 'uptime'),
      names: uptimeNames,
      phase: phaseFor(uptimeNames, uptimeNow != null),
      value: uptimeNow == null ? '--' : formatDuration(uptimeNow),
      unit: '',
      alertLevel: alerts.uptime
    }
  ];
  const charts = [
    <ThinTimeSeries
      key="cpu"
      title={hostCategoryText(t, 'cpuUtilization')}
      loading={cpuPhase === 'loading'}
      unit="percent"
      data={metricHasPoints(metrics.cpu_usage_total) ? cpuTrend : []}
      emptyText={cpuPhase === 'error' ? '加载失败' : '暂无数据'}
      onRetry={cpuPhase === 'error' ? retry(cpuNames) : undefined}
      legends={[{
        label: 'CPU',
        color: CPU_SERIES_COLOR
      }]}
    />,
    <ThinTimeSeries
      key="mem"
      title={hostCategoryText(t, 'memoryUtilization')}
      loading={memPhase === 'loading'}
      unit="percent"
      data={memChart.data}
      emptyText={memPhase === 'error' ? '加载失败' : '暂无数据'}
      onRetry={memPhase === 'error' ? retry(memTrendNames) : undefined}
      legends={memItems.map((item) => ({
        label: item.label,
        color: item.color
      }))}
    />,
    loadActive ? (
      <ThinTimeSeries
        key="load"
        title="负载"
        loading={loadPhase === 'loading'}
        unit="none"
        data={loadTrend}
        emptyText={loadPhase === 'error' ? '加载失败' : '暂无数据'}
        onRetry={loadPhase === 'error' ? retry(loadNames) : undefined}
        legends={loadItems.map((item) => ({
          label: item.label,
          color: item.color
        }))}
      />
    ) : null
  ].filter(Boolean);
  const gridClass = charts.length >= 3 ? styles.chartGrid3 : charts.length === 2 ? styles.chartGrid2 : styles.chartGrid;
  const swapNames = ['host_mem_swap_used_bytes', 'host_mem_swap_total_bytes', 'mem_swap_free'] as const;
  const swapTrend = useMemo(() => {
    const total = metrics.host_mem_swap_total_bytes?.viewData;
    const used = primaryChartSeries(metrics.host_mem_swap_used_bytes?.viewData);
    const fromUsed = used.length ? deriveRatioPercent(used, total) : [];
    if (fromUsed.length) return fromUsed;
    const derivedUsed = subtractAligned(total, metrics.mem_swap_free?.viewData);
    return deriveRatioPercent(derivedUsed, total);
  }, [
    metrics.host_mem_swap_total_bytes?.viewData,
    metrics.host_mem_swap_used_bytes?.viewData,
    metrics.mem_swap_free?.viewData
  ]);
  const swapPhase = phaseFor(swapNames, swapTrend.length > 0);
  const memoryParts = useMemo(() => {
    const total = metrics.mem_total?.viewData;
    const usedBytes = metricHasPoints(metrics.mem_used)
      ? primaryChartSeries(metrics.mem_used?.viewData)
      : subtractAligned(total, metrics.mem_available?.viewData);
    const raw: Record<string, ChartData[]> = {
      mem_used: usedBytes,
      mem_cached: primaryChartSeries(metrics.mem_cached?.viewData),
      mem_buffered: primaryChartSeries(metrics.mem_buffered?.viewData),
      mem_shared: primaryChartSeries(metrics.mem_shared?.viewData)
    };
    return MEM_COMPOSITION.flatMap((item) => {
      const bytes = latestSeriesValue(raw[item.key]);
      if (bytes == null || bytes <= 0) return [];
      return [{ ...item, bytes }];
    });
  }, [
    metrics.mem_available?.viewData,
    metrics.mem_available?.loadState,
    metrics.mem_buffered?.viewData,
    metrics.mem_buffered?.loadState,
    metrics.mem_cached?.viewData,
    metrics.mem_cached?.loadState,
    metrics.mem_shared?.viewData,
    metrics.mem_shared?.loadState,
    metrics.mem_total?.viewData,
    metrics.mem_total?.loadState,
    metrics.mem_used?.viewData,
    metrics.mem_used?.loadState
  ]);
  const memoryBytes = memoryParts.reduce((sum, item) => sum + item.bytes, 0);
  const gpuCharts = GPU_SERIES.filter((item) => metricHasPoints(metrics[item.key]));

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>关键指标</div>
      </div>
      <div className={styles.instantKpiRow}>
        {instantCards.map((card) => (
          <section key={card.key} className={`${classic.panel} ${styles.instantKpi} ${cardAlertClass(card.alertLevel)}`}>
            <CardAlertDot level={card.alertLevel} valueColor={card.valueColor} />
            <div className={styles.instantKpiLabel}>{card.label}</div>
            {card.phase === 'loading' ? (
              <span
                className="mt-1 block h-4 w-16 rounded bg-[var(--color-fill-2)]"
                aria-busy="true"
                aria-label="加载中"
              />
            ) : card.phase === 'error' ? (
              <button
                type="button"
                className="mt-1 text-left text-[12px] text-[var(--color-text-3)]"
                onClick={retry(card.names)}
              >
                加载失败，重试
              </button>
            ) : (
              <div
                className={styles.instantKpiValue}
                style={card.valueColor ? { color: card.valueColor } : undefined}
              >
                {card.value}
                {card.unit ? <span className={styles.instantKpiUnit}>{card.unit}</span> : null}
              </div>
            )}
          </section>
        ))}
      </div>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>本机趋势</div>
      </div>
      <div className={gridClass}>{charts}</div>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'detailedMetrics')}</div>
      </div>
      <div className={styles.detailTrio}>
        <ThinTimeSeries
          className={styles.detailCard}
          title={hostCategoryText(t, 'swapSpaceUsage')}
          subtitle={hostCategoryText(t, 'swapSpaceUsageSubtitle')}
          hint={hostCategoryText(t, 'swapSpaceUsageHint')}
          loading={swapPhase === 'loading'}
          unit="percent"
          data={swapTrend}
          emptyText={swapPhase === 'error' ? '加载失败' : '暂无数据'}
          onRetry={swapPhase === 'error' ? retry(swapNames) : undefined}
          showSeriesName
          legends={[{ label: '已用占比', color: SWAP_SERIES_COLOR }]}
        />
        <section className={`${classic.panel} ${styles.chartPanel} ${styles.detailCard} ${styles.detailSlot}`} data-surface="memory">
          <div className={styles.chartHead}>
            <div className={styles.chartTitle}>{hostCategoryText(t, 'memoryComposition')}</div>
          </div>
          {memoryBytes > 0 ? (
            <div className={styles.compositionBody}>
              <div className={styles.compositionBar} aria-hidden="true">
                {memoryParts.map((item) => (
                  <span
                    key={item.key}
                    style={{ width: `${(item.bytes / memoryBytes) * 100}%`, background: item.color }}
                  />
                ))}
              </div>
              <div className={`${styles.chartLegend} ${styles.compositionLegend}`}>
                {memoryParts.map((item) => (
                  <span key={item.key}>
                    <span className={styles.legendSwatch} style={{ background: item.color }} />
                    {item.label}
                    <span className={styles.legendReading} style={{ color: item.color }}>{formatBytes(item.bytes)}</span>
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <div className={styles.chartEmpty}>—</div>
          )}
        </section>
        <ThinTimeSeries
          className={styles.detailCard}
          title={hostCategoryText(t, 'cpuTimeBreakdown')}
          loading={breakdownPhase === 'loading'}
          unit="percent"
          data={breakdownTrend}
          emptyText={breakdownPhase === 'error' ? '加载失败' : '暂无数据'}
          onRetry={breakdownPhase === 'error' ? retry(breakdownNames) : undefined}
          legends={breakdown.map((item) => ({
            label: item.label,
            color: item.color
          }))}
        />
      </div>
      <div className={styles.detailFull} data-surface="gpu">
        {gpuCharts.length ? (
          <div className={styles.gpuRow}>
            {GPU_SERIES.map((item) => (
              <ThinTimeSeries
                key={item.key}
                className={styles.detailCard}
                title={item.title}
                unit={item.unit}
                data={primaryChartSeries(metrics[item.key]?.viewData)}
                emptyText="暂无数据"
                legends={[{
                  label: item.title,
                  color: item.key === 'nvidia_smi_temperature_gpu'
                    ? HOST_PALETTE.orange
                    : item.key === 'nvidia_smi_utilization_memory'
                      ? HOST_PALETTE.blue
                      : HOST_PALETTE.emerald
                }]}
              />
            ))}
          </div>
        ) : (
          <section className={`${classic.panel} ${styles.chartPanel} ${styles.detailCard} ${styles.gpuBand}`}>
            <div className={styles.chartHead}>
              <div className={styles.chartTitle}>GPU</div>
            </div>
            <div className={styles.gpuEmpty}>{hostCategoryText(t, 'noGpu')}</div>
          </section>
        )}
      </div>
    </>
  );
}
