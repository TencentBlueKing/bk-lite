'use client';

import React, { useMemo, useState } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { hostCategoryText } from './category-copy';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../config';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import { CardAlertDot, cardAlertClass, type CardAlertFold } from './card-alert';
import ThinTimeSeries from './thin-time-series';
import type { HostSurfaceAlerts } from './tab-level';
import { metricBlockPhase, type MetricBlockPhase } from './performance-scope';
import {
  formatPlain,
  formatSharedBytePair,
  latestNumber,
  metricHasPoints,
  numericValue,
  primaryChartSeries,
  resolveMemoryUsage
} from './readings';
import ProDashLoading from './pro-dash-loading';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

/** system / steal 没有对应的序列 token，色值跟构成表。 */
const CPU_SYSTEM_COLOR = '#86909C';
const CPU_STEAL_COLOR = '#F5319D';
const CPU_SOFTIRQ_COLOR = HOST_PALETTE.cyan;

const CPU_BREAKDOWN = [
  { key: 'cpu_usage_user_total', label: 'user', color: HOST_SERIES_COLOR.cpu },
  { key: 'cpu_usage_system_total', label: 'system', color: CPU_SYSTEM_COLOR },
  { key: 'cpu_usage_iowait_total', label: 'iowait', color: HOST_SERIES_COLOR.load1 },
  { key: 'cpu_usage_irq_total', label: 'irq', color: HOST_SERIES_COLOR.diskUsed },
  { key: 'cpu_usage_softirq_total', label: 'softirq', color: CPU_SOFTIRQ_COLOR },
  { key: 'cpu_usage_steal_total', label: 'steal', color: CPU_STEAL_COLOR }
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
  { key: 'mem_cached', label: 'cached', color: HOST_SERIES_COLOR.memAvailable },
  { key: 'mem_buffered', label: 'buffered', color: HOST_SERIES_COLOR.load5 },
  { key: 'mem_shared', label: 'shared', color: HOST_SERIES_COLOR.diskUsed }
] as const;

const GPU_CHARTS = [
  { key: 'nvidia_smi_utilization_gpu', titleKey: 'gpuUtilization' as const, unit: 'percent' as const },
  { key: 'nvidia_smi_memory_used', titleKey: 'gpuMemoryUsed' as const, unit: 'mebibytes' as const },
  { key: 'nvidia_smi_temperature_gpu', titleKey: 'gpuTemperature' as const, unit: 'celsius' as const }
] as const;

const SWAP_SERIES_COLOR = HOST_PALETTE.emerald;

const gpuCardTitle = (row: EntityTableRow, fallback: string) => {
  const index = row.labels.index;
  const name = row.labels.name;
  if (index && name) return `${fallback} ${index} · ${name}`;
  if (index) return `${fallback} ${index}`;
  if (name) return name;
  return fallback;
};

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

const formatMebibytes = (value: number) => {
  const formatted = formatMetricValue(value, 'mebibytes');
  return `${formatted.value}${formatted.unit || ''}`;
};

const formatPercent = (value: number) => {
  const formatted = formatMetricValue(value, 'percent');
  return `${formatted.value}${formatted.unit || ''}`;
};

interface ComposeSlice {
  key: string;
  label: string;
  color: string;
  amount: number;
  reading: string;
}

type ComposeView = 'pie' | 'line';

function ComposeViewSwitch({
  value,
  onChange,
  pieLabel,
  lineLabel
}: {
  value: ComposeView;
  onChange: (next: ComposeView) => void;
  pieLabel: string;
  lineLabel: string;
}) {
  const option = (mode: ComposeView, label: string) => (
    <button
      type="button"
      aria-pressed={value === mode}
      className={value === mode
        ? 'rounded px-2 py-0.5 text-[12px] font-semibold text-[var(--color-primary)] bg-[var(--color-primary-bg-active)]'
        : 'rounded px-2 py-0.5 text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-text-2)]'}
      onClick={() => onChange(mode)}
    >
      {label}
    </button>
  );
  return (
    <div
      className="inline-flex shrink-0 items-center rounded-md border border-[var(--color-border)] p-0.5"
      role="group"
    >
      {option('pie', pieLabel)}
      {option('line', lineLabel)}
    </div>
  );
}

const PIE_CX = 50;
const PIE_CY = 50;
const PIE_R = 34;
/** viewBox 100 配 120px 宽时，8 个单位约 9.6px。 */
const PIE_EXPLODE = 8;
/** 与次高相差不足 0.5 个百分点时，只强调序列里先出现的那一段。 */
const PIE_TIE_GAP = 0.005;

const piePoint = (cx: number, cy: number, radius: number, angle: number) => ({
  x: cx + radius * Math.cos(angle),
  y: cy + radius * Math.sin(angle)
});

const pieSlicePath = (start: number, sweep: number, offset: number) => {
  const mid = start + sweep / 2;
  const cx = PIE_CX + Math.cos(mid) * offset;
  const cy = PIE_CY + Math.sin(mid) * offset;
  const from = piePoint(cx, cy, PIE_R, start);
  const to = piePoint(cx, cy, PIE_R, start + sweep);
  const large = sweep > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${from.x} ${from.y} A ${PIE_R} ${PIE_R} 0 ${large} 1 ${to.x} ${to.y} Z`;
};

/**
 * 左实心饼、右图例。饼心不写字。
 * 占比最高的一片沿角平分线外移；满圆不外移。
 * 并列最大时只强调先出现的一段，不把多片一起炸开。
 */
function CompositionDonut({ slices }: { slices: ComposeSlice[] }) {
  const total = slices.reduce((sum, slice) => sum + slice.amount, 0);
  let leadIndex = 0;
  slices.forEach((slice, index) => {
    if (slice.amount > slices[leadIndex].amount) leadIndex = index;
  });
  const secondAmount = slices.reduce((best, slice, index) => (
    index === leadIndex ? best : Math.max(best, slice.amount)
  ), 0);
  const tied = slices.length > 1 && total > 0 && (slices[leadIndex].amount - secondAmount) / total < PIE_TIE_GAP;
  const emphasizeIndex = tied ? slices.findIndex((slice) => slice.amount === slices[leadIndex].amount) : leadIndex;
  let cursor = -Math.PI / 2;
  const wedges = slices.map((slice, index) => {
    const sweep = total > 0 ? (slice.amount / total) * Math.PI * 2 : 0;
    const full = slices.length === 1 || sweep >= Math.PI * 2 - 0.001;
    const explode = index === emphasizeIndex && !full;
    const start = cursor;
    cursor += sweep;
    return { slice, start, sweep, explode, lead: index === emphasizeIndex };
  });
  return (
    <div className={styles.composeBody}>
      <svg className={styles.composePie} viewBox="0 0 100 100" aria-hidden="true">
        {wedges.map((wedge) => (
          wedge.sweep >= Math.PI * 2 - 0.001 ? (
            <circle key={wedge.slice.key} cx={PIE_CX} cy={PIE_CY} r={PIE_R} fill={wedge.slice.color} />
          ) : (
            <path
              key={wedge.slice.key}
              d={pieSlicePath(wedge.start, wedge.sweep, wedge.explode ? PIE_EXPLODE : 0)}
              fill={wedge.slice.color}
              stroke="var(--color-bg)"
              strokeWidth="1"
            />
          )
        ))}
      </svg>
      <ul className={styles.composeLegend}>
        {wedges.map((wedge) => (
          <li key={wedge.slice.key} className={wedge.lead ? styles.leadRow : undefined}>
            <span className={styles.legendSwatch} style={{ background: wedge.slice.color }} />
            <span className={styles.composeName}>{wedge.slice.label}</span>
            <span className={styles.composeReading}>{wedge.slice.reading}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SystemPane({
  metrics,
  pendingMetricNames = EMPTY_PENDING,
  onRetryMetrics,
  alerts,
  gpuRows = [],
  gpuLoading = false
}: {
  metrics: Record<string, MetricSeries | undefined>;
  pendingMetricNames?: ReadonlySet<string>;
  onRetryMetrics?: (names: string[]) => void;
  alerts: HostSurfaceAlerts['system'];
  gpuRows?: EntityTableRow[];
  gpuLoading?: boolean;
}) {
  const { t } = useDashboardText();
  const [memoryView, setMemoryView] = useState<ComposeView>('pie');
  const [cpuView, setCpuView] = useState<ComposeView>('pie');

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
  const cpuSlices = useMemo(() => (
    CPU_BREAKDOWN.flatMap((item) => {
      const value = latestNumber(metrics[item.key]);
      if (value == null || value <= 0) return [];
      return [{ ...item, amount: value, reading: formatPercent(value) }];
    })
  ), [
    metrics.cpu_usage_user_total?.viewData,
    metrics.cpu_usage_user_total?.loadState,
    metrics.cpu_usage_system_total?.viewData,
    metrics.cpu_usage_system_total?.loadState,
    metrics.cpu_usage_iowait_total?.viewData,
    metrics.cpu_usage_iowait_total?.loadState,
    metrics.cpu_usage_irq_total?.viewData,
    metrics.cpu_usage_irq_total?.loadState,
    metrics.cpu_usage_softirq_total?.viewData,
    metrics.cpu_usage_softirq_total?.loadState,
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
  const showLoad = metricHasPoints(metrics.system_load1);
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
    fold?: CardAlertFold;
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
    ...(showLoad ? [{
      key: 'load',
      label: hostCategoryText(t, 'loadOneMinute'),
      names: load1Names,
      phase: phaseFor(load1Names, load1Now != null),
      value: formatPlain(load1Now),
      unit: '',
      valueColor: LOAD1_SERIES_COLOR,
      alertLevel: alerts.load,
      fold: alerts.load === 'warn' ? 'outline' as const : undefined
    }] : []),
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
  const swapUsedSeries = useMemo(() => {
    const used = primaryChartSeries(metrics.host_mem_swap_used_bytes?.viewData);
    if (used.length) return used;
    return subtractAligned(metrics.host_mem_swap_total_bytes?.viewData, metrics.mem_swap_free?.viewData);
  }, [
    metrics.host_mem_swap_total_bytes?.viewData,
    metrics.host_mem_swap_used_bytes?.viewData,
    metrics.mem_swap_free?.viewData
  ]);
  const swapPhase = phaseFor(swapNames, swapUsedSeries.length > 0);
  const swapUsedNow = latestSeriesValue(swapUsedSeries);
  const swapTotalNow = latestNumber(metrics.host_mem_swap_total_bytes);
  const swapHasSeries = swapUsedSeries.length > 0;
  const swapReading = swapUsedNow == null ? '--' : formatSharedBytePair(swapUsedNow, swapTotalNow);
  const memoryCompose = useMemo(() => {
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
    const series = MEM_COMPOSITION.flatMap((item) => {
      const data = raw[item.key] || [];
      if (!data.length) return [];
      return [{ ...item, data }];
    });
    const parts = series.flatMap((item) => {
      const bytes = latestSeriesValue(item.data);
      if (bytes == null || bytes <= 0) return [];
      return [{ ...item, bytes }];
    });
    return {
      parts,
      series,
      trend: series.length
        ? mergeChartSeries(series.map((item) => ({ key: item.key, label: item.label, data: item.data })))
        : []
    };
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
  const memoryBytes = memoryCompose.parts.reduce((sum, item) => sum + item.bytes, 0);
  const composeNames = ['mem_used', 'mem_cached', 'mem_buffered', 'mem_shared', 'mem_total', 'mem_available'] as const;
  const composeLoading = phaseFor(composeNames, memoryCompose.series.length > 0) === 'loading';
  const cpuCompose = useMemo(() => {
    const series = CPU_BREAKDOWN.flatMap((item) => {
      const data = primaryChartSeries(metrics[item.key]?.viewData);
      if (!data.length) return [];
      return [{ ...item, data }];
    });
    return {
      series,
      trend: series.length
        ? mergeChartSeries(series.map((item) => ({ key: item.key, label: item.label, data: item.data })))
        : []
    };
  }, [
    metrics.cpu_usage_user_total?.viewData,
    metrics.cpu_usage_system_total?.viewData,
    metrics.cpu_usage_iowait_total?.viewData,
    metrics.cpu_usage_irq_total?.viewData,
    metrics.cpu_usage_softirq_total?.viewData,
    metrics.cpu_usage_steal_total?.viewData
  ]);
  const gpuMemReadingOf = (row: EntityTableRow) => {
    const used = row.values.nvidia_smi_memory_used;
    const total = row.values.nvidia_smi_memory_total;
    if (used == null || !Number.isFinite(used)) return undefined;
    if (total == null || !Number.isFinite(total)) return formatMebibytes(used);
    return `${formatMebibytes(used)} / ${formatMebibytes(total)}`;
  };

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>关键指标</div>
      </div>
      <div className={styles.instantKpiRow}>
        {instantCards.map((card) => (
          <section key={card.key} className={`${classic.panel} ${styles.instantKpi} ${cardAlertClass(card.alertLevel)}`}>
            <CardAlertDot level={card.alertLevel} fold={card.fold} />
            <div className={styles.instantKpiLabel}>{card.label}</div>
            {card.phase === 'loading' ? (
              <ProDashLoading size="small" layout="inline" />
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
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'viewTrend')}</div>
      </div>
      <div className={gridClass}>{charts}</div>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'detailedMetrics')}</div>
      </div>
      <div className={styles.detailTrio}>
        <section className={`${classic.panel} ${styles.chartPanel} ${styles.detailCard} ${styles.detailSlot}`} data-surface="memory">
          <div className={styles.chartHead}>
            <div className={styles.chartTitle}>{hostCategoryText(t, 'memoryComposition')}</div>
            <ComposeViewSwitch
              value={memoryView}
              onChange={setMemoryView}
              pieLabel={hostCategoryText(t, 'composePie')}
              lineLabel={hostCategoryText(t, 'composeLine')}
            />
          </div>
          {memoryView === 'line' ? (
            <ThinTimeSeries
              bare
              title=""
              unit="bytes"
              loading={composeLoading}
              data={memoryCompose.trend}
              emptyText="暂无数据"
              legends={memoryCompose.series.map((item) => ({ label: item.label, color: item.color }))}
            />
          ) : composeLoading ? (
            <div className={styles.chartBody}>
              <div className={styles.chartEmpty}>
                <ProDashLoading />
              </div>
            </div>
          ) : memoryBytes > 0 ? (
            <CompositionDonut
              slices={memoryCompose.parts.map((item) => ({
                key: item.key,
                label: item.label,
                color: item.color,
                amount: item.bytes,
                reading: `${formatBytes(item.bytes)} ${((item.bytes / memoryBytes) * 100).toFixed(1)}%`
              }))}
            />
          ) : (
            <div className={styles.chartEmpty}>—</div>
          )}
        </section>
        <section className={`${classic.panel} ${styles.chartPanel} ${styles.detailCard} ${styles.detailSlot}`} data-surface="cpu-time">
          <div className={styles.chartHead}>
            <div className={styles.chartTitle}>{hostCategoryText(t, 'cpuTimeBreakdown')}</div>
            <ComposeViewSwitch
              value={cpuView}
              onChange={setCpuView}
              pieLabel={hostCategoryText(t, 'composePie')}
              lineLabel={hostCategoryText(t, 'composeLine')}
            />
          </div>
          {breakdownPhase === 'loading' ? (
            <div className={styles.chartBody}>
              <div className={styles.chartEmpty}>
                <ProDashLoading />
              </div>
            </div>
          ) : breakdownPhase === 'error' ? (
            <button
              type="button"
              className="mt-1 text-left text-[12px] text-[var(--color-text-3)]"
              onClick={retry(breakdownNames)}
            >
              加载失败，重试
            </button>
          ) : cpuView === 'line' ? (
            <ThinTimeSeries
              bare
              title=""
              unit="percent"
              data={cpuCompose.trend}
              emptyText="暂无数据"
              legends={cpuCompose.series.map((item) => ({ label: item.label, color: item.color }))}
            />
          ) : cpuSlices.length ? (
            <CompositionDonut slices={cpuSlices} />
          ) : (
            <div className={styles.chartEmpty}>暂无数据</div>
          )}
        </section>
        <ThinTimeSeries
          className={styles.detailCard}
          title={hostCategoryText(t, 'swapUtilization')}
          hint={hostCategoryText(t, swapHasSeries ? 'swapUsedHint' : 'swapAbsentHint')}
          reading={swapReading}
          loading={swapPhase === 'loading'}
          unit="bytes"
          data={swapUsedSeries}
          emptyText={swapPhase === 'error' ? '加载失败' : '暂无数据'}
          onRetry={swapPhase === 'error' ? retry(swapNames) : undefined}
          legends={[{ label: '已用', color: SWAP_SERIES_COLOR }]}
        />
      </div>
      {gpuRows.length ? (
        <div className={styles.detailFull} data-surface="gpu">
          {gpuRows.map((row) => {
            const bandTitle = gpuRows.length > 1 ? gpuCardTitle(row, 'GPU') : 'GPU';
            return (
              <div key={row.key} className={styles.gpuBand}>
                <div className={styles.gpuBandTitle}>{bandTitle}</div>
                <div className={styles.gpuRow}>
                  {GPU_CHARTS.map((item) => {
                    const title = hostCategoryText(t, item.titleKey);
                    const points = row.series[item.key] || [];
                    return (
                      <ThinTimeSeries
                        key={item.key}
                        className={styles.detailCard}
                        title={title}
                        unit={item.unit}
                        data={pointsToChartData(points.length ? [{ points }] : [])}
                        emptyText="暂无数据"
                        reading={item.key === 'nvidia_smi_memory_used' ? gpuMemReadingOf(row) : undefined}
                        legends={[{
                          label: title,
                          color: item.key === 'nvidia_smi_temperature_gpu'
                            ? HOST_PALETTE.orange
                            : item.key === 'nvidia_smi_memory_used'
                              ? HOST_PALETTE.blue
                              : HOST_PALETTE.emerald
                        }]}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : gpuLoading ? (
        <div className={styles.detailFull} data-surface="gpu">
          <div className={styles.gpuBand}>
            <div className={styles.gpuBandTitle}>GPU</div>
            <span
              className="block h-4 w-16 rounded bg-[var(--color-fill-2)]"
              aria-busy="true"
              aria-label="加载中"
            />
          </div>
        </div>
      ) : null}
    </>
  );
}
