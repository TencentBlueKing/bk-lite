'use client';

import React, { useMemo } from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { hostCategoryText } from './category-copy';
import { HOST_SERIES_COLOR } from '../config';
import {
  latestPreferSignal,
  pointsToChartData,
  sumPoints,
  type EntityTableRow
} from '../entity-series';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import EventsRail, { type HostAlertRailEvent } from './events-rail';
import { metricBlockPhase } from './performance-scope';
import ProDashLoading from './pro-dash-loading';
import {
  EVENT_RAIL_HINT_LINES,
  KpiStrip,
  ProFocusCard,
  ProInfoHint,
  ProSection,
  proChromeClass,
  type KpiCardModel
} from './pro-chrome';
import ThinTimeSeries from './thin-time-series';
import FocusShortcutTitle from './focus-shortcut-title';
import { describeFocusAxis, formatFocusHeadline, seriesSampleValues } from './focus-axis';
import { useProTimeWindow } from './pro-time-window';
import { loadPerCore, type HostSurfaceAlerts } from './tab-level';
import {
  formatPercent,
  formatPlain,
  formatUnit,
  latestNumber,
  metricHasPoints,
  primaryChartSeries,
  resolveMemoryUsage
} from './readings';
import styles from './layered.module.scss';

interface OverviewPaneProps {
  metrics: Record<string, MetricSeries | undefined>;
  loading: boolean;
  diskRows: EntityTableRow[];
  diskLoading: boolean;
  netRows: EntityTableRow[];
  netLoading?: boolean;
  processRows: EntityTableRow[];
  processReady: boolean;
  processLoading?: boolean;
  alertCount: number | null;
  alertEvents?: HostAlertRailEvent[];
  eventsLoading?: boolean;
  alertsOpen?: boolean;
  pendingMetricNames?: ReadonlySet<string>;
  onOpenAlerts?: () => void;
  onFocusAlert?: (alertId: string) => void;
  onJump: (tab: 'disk' | 'net' | 'process', key: string) => void;
  alerts: HostSurfaceAlerts['overview'];
}

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

const latestOfRow = (row: EntityTableRow | undefined, key: string) => {
  const value = row?.values[key];
  return value == null || !Number.isFinite(value) ? null : value;
};

/** 快捷卡：优先用序列防末段掉零；无序列时回退 values。 */
const readingOfRow = (row: EntityTableRow | undefined, key: string) => {
  const fromSeries = latestPreferSignal(row?.series[key]);
  if (fromSeries != null) return fromSeries;
  return latestOfRow(row, key);
};

const finiteByTime = (points: Array<{ time: number; value: number }> | undefined) => {
  const map = new Map<number, number>();
  (points || []).forEach((point) => {
    if (Number.isFinite(point.time) && Number.isFinite(point.value)) map.set(point.time, point.value);
  });
  return map;
};

/**
 * 总使用率 = 100 × Σ已用 / Σ总量。
 * 同一时刻已用优先用总量减空闲，否则用总量 × 使用率；没有总量的挂载不进合计。
 * 与挂载行 disk_used 的推法一致，按时刻对所有挂载加权。
 */
const hostDiskUsagePoints = (rows: EntityTableRow[]) => {
  const buckets = new Map<number, { used: number; total: number }>();
  rows.forEach((row) => {
    const totals = finiteByTime(row.series.disk_total);
    const frees = finiteByTime(row.series.disk_free);
    const percents = finiteByTime(row.series.disk_used_percent);
    totals.forEach((total, time) => {
      if (total <= 0) return;
      const free = frees.get(time);
      const percent = percents.get(time);
      const used = free != null
        ? Math.max(0, total - free)
        : percent != null
          ? Math.max(0, total * percent / 100)
          : null;
      if (used == null) return;
      const bucket = buckets.get(time) || { used: 0, total: 0 };
      bucket.used += used;
      bucket.total += total;
      buckets.set(time, bucket);
    });
  });
  return Array.from(buckets.entries())
    .filter(([, bucket]) => bucket.total > 0)
    .sort((left, right) => left[0] - right[0])
    .map(([time, bucket]) => ({ time, value: (100 * bucket.used) / bucket.total }));
};

/** 与性能页同名曲线共用序列色。负载跟 load1 橙，不读旧图表的靛色。 */
const CPU_SERIES = { label: 'CPU', color: HOST_SERIES_COLOR.cpu };
const DISK_TOTAL_SERIES = { label: '总使用率', color: HOST_SERIES_COLOR.diskUsed };
const MEM_SERIES = { label: '内存', color: HOST_SERIES_COLOR.memUsed };
const LOAD1_SERIES_COLOR = HOST_SERIES_COLOR.load1;


export default function OverviewPane({
  metrics,
  loading,
  diskRows,
  diskLoading,
  netRows,
  netLoading = false,
  processRows,
  processLoading = false,
  alertCount,
  alertEvents = [],
  eventsLoading = false,
  alertsOpen = false,
  pendingMetricNames = EMPTY_PENDING,
  onOpenAlerts,
  onFocusAlert,
  onJump,
  alerts
}: OverviewPaneProps) {
  const { t } = useDashboardText();
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;
  const worst = diskRows[0];
  const busiest = netRows[0];
  const topProcess = processRows[0];
  const cpu = latestNumber(metrics.cpu_usage_total);
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
  const mem = memoryUsage.usedNow;
  const load = latestNumber(metrics.system_load1);
  const cpuCores = latestNumber(metrics.cpu_n);
  const loadEachCore = loadPerCore(load, cpuCores);
  const uptime = latestNumber(metrics.system_uptime);
  const showLoad = metricHasPoints(metrics.system_load1);
  const diskUsagePoints = useMemo(() => hostDiskUsagePoints(diskRows), [diskRows]);
  const diskCurrent = readingOfRow(worst, 'disk_used_percent');
  const mountName = worst?.labels.path || worst?.labels.mount || '';

  const cards = useMemo<KpiCardModel[]>(() => {
    const items: KpiCardModel[] = [
      {
        key: 'cpu',
        label: 'CPU',
        value: formatPercent(cpu),
        tone: CPU_SERIES.color,
        alertLevel: alerts.cpu
      },
      {
        key: 'mem',
        label: '内存',
        value: formatPercent(mem),
        tone: MEM_SERIES.color,
        alertLevel: alerts.mem
      }
    ];
    if (showLoad) {
      items.push({
        key: 'load',
        label: hostCategoryText(t, 'loadOneMinute'),
        value: formatPlain(load),
        tone: LOAD1_SERIES_COLOR,
        alertLevel: alerts.load,
        fold: alerts.load === 'warn' ? 'outline' : undefined,
        subtitle: cpuCores != null && cpuCores > 0 && loadEachCore != null
          ? hostCategoryText(t, 'loadCoresAside', {
            cores: formatPlain(cpuCores, 0),
            perCore: formatPlain(loadEachCore)
          })
          : undefined
      });
    }
    items.push({
      key: 'disk',
      label: hostCategoryText(t, 'diskTotalUsage'),
      hint: hostCategoryText(t, 'diskUsageHint'),
      value: formatPercent(diskCurrent),
      tone: HOST_SERIES_COLOR.diskUsed,
      subtitle: mountName || undefined,
      alertLevel: alerts.disk
    });
    const alertTone = alertCount == null
      ? undefined
      : alertCount > 0
        ? 'var(--color-fail)'
        : 'var(--color-success)';
    items.push({
      key: 'uptime',
      label: hostCategoryText(t, 'uptime'),
      value: uptime == null ? '--' : formatDuration(uptime),
      alertLevel: alerts.uptime
    });
    items.push({
      key: 'alert',
      label: '告警',
      value: alertCount == null ? '--' : String(alertCount),
      tone: alertTone,
      onActivate: onOpenAlerts,
      expanded: alertsOpen
    });
    return items;
  }, [
    alertCount,
    alertsOpen,
    cpu,
    cpuCores,
    diskCurrent,
    mountName,
    load,
    loadEachCore,
    mem,
    alerts,
    onOpenAlerts,
    showLoad,
    uptime,
    t
  ]);

  const netIn = latestNumber(metrics.net_bytes_recv_rate);
  const netOut = latestNumber(metrics.net_bytes_sent_rate);
  const cpuTrend = useMemo(
    () => primaryChartSeries(metrics.cpu_usage_total?.viewData),
    [metrics.cpu_usage_total?.viewData]
  );
  const memTrend = memoryUsage.used;
  const netTrend = useMemo(() => mergeChartSeries([
    { key: 'in', label: '入', data: primaryChartSeries(metrics.net_bytes_recv_rate?.viewData) },
    { key: 'out', label: '出', data: primaryChartSeries(metrics.net_bytes_sent_rate?.viewData) }
  ]), [metrics.net_bytes_recv_rate?.viewData, metrics.net_bytes_sent_rate?.viewData]);
  const diskTrend = useMemo(
    () => (worst ? pointsToChartData([{ points: worst.series.disk_used_percent || [] }]) : []),
    [worst]
  );
  const diskUsageTrend = useMemo(
    () => pointsToChartData([{ points: diskUsagePoints }]),
    [diskUsagePoints]
  );
  const nicThroughput = busiest == null
    ? null
    : (() => {
      const inbound = readingOfRow(busiest, 'net_bytes_recv_rate');
      const outbound = readingOfRow(busiest, 'net_bytes_sent_rate');
      if (inbound == null && outbound == null) return null;
      if (netLoading && (inbound == null || outbound == null)) return null;
      return (inbound ?? 0) + (outbound ?? 0);
    })();
  const nicTrend = useMemo(
    () => (busiest
      ? pointsToChartData([{
        points: sumPoints(busiest.series.net_bytes_recv_rate, busiest.series.net_bytes_sent_rate)
      }])
      : []),
    [busiest]
  );
  const processTrend = useMemo(
    () => (topProcess
      ? pointsToChartData([{ points: topProcess.series.process_cpu_usage || [] }])
      : []),
    [topProcess]
  );
  const chartLoading = (names: readonly string[], hasValue: boolean) => (
    metricBlockPhase(names, pendingMetricNames, loadStateOf(metrics, names), hasValue) === 'loading'
  );
  const diskFocus = worst
    ? describeFocusAxis('percent', seriesSampleValues(clipChartDataToWindow(diskTrend, chartWindow)))
    : null;
  const nicFocus = busiest
    ? describeFocusAxis('byteps', seriesSampleValues(clipChartDataToWindow(nicTrend, chartWindow)))
    : null;
  const processFocus = topProcess
    ? describeFocusAxis('percent', seriesSampleValues(clipChartDataToWindow(processTrend, chartWindow)))
    : null;

  return (
    <>
      <ProSection title="健康概览">
        <KpiStrip items={cards} loading={loading} />
      </ProSection>
      <ProSection
        title={hostCategoryText(t, 'events')}
        hint={<ProInfoHint kind="events" lines={EVENT_RAIL_HINT_LINES} />}
      >
        <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />
      </ProSection>

      <ProSection title="重点关注">
      <div className={`${proChromeClass.shortcutGrid} ${styles.shortcutGrid3}`}>
        <ProFocusCard key="disk">
          <div className={proChromeClass.shortcutCopy}>
            <FocusShortcutTitle
              label={hostCategoryText(t, 'busiestMount')}
              unit={diskFocus?.unitLabel}
            />
            {worst ? (
              <>
                <div className={proChromeClass.shortcutMain}>{mountName || '—'}</div>
                <div className={proChromeClass.shortcutValue} style={{ color: HOST_SERIES_COLOR.diskUsed }}>
                  {diskFocus ? formatFocusHeadline(diskFocus, diskCurrent) : '--'}
                </div>
                <button type="button" className={proChromeClass.jumpBtn} onClick={() => onJump('disk', worst.key)}>
                  查看磁盘
                </button>
              </>
            ) : diskLoading ? (
              <ProDashLoading size="small" />
            ) : (
              <div className={proChromeClass.shortcutSub}>暂无挂载数据</div>
            )}
          </div>
          {worst ? (
            <ThinTimeSeries
              bare
              numericAxis
              className={proChromeClass.focusChart}
              title=""
              unit="percent"
              data={diskTrend}
              legends={[{ label: '使用率', color: HOST_SERIES_COLOR.diskUsed }]}
            />
          ) : null}
        </ProFocusCard>
        <ProFocusCard key="net">
          <div className={proChromeClass.shortcutCopy}>
            <FocusShortcutTitle
              label={hostCategoryText(t, 'busiestNic')}
              unit={nicFocus?.unitLabel}
            />
            {busiest ? (
              <>
                <div className={proChromeClass.shortcutMain}>{busiest.labels.interface || '—'}</div>
                <div className={proChromeClass.shortcutValue} style={{ color: HOST_SERIES_COLOR.netIn }}>
                  {nicFocus ? formatFocusHeadline(nicFocus, nicThroughput) : '--'}
                </div>
                <button type="button" className={proChromeClass.jumpBtn} onClick={() => onJump('net', busiest.key)}>
                  查看网络
                </button>
              </>
            ) : netLoading ? (
              <ProDashLoading size="small" />
            ) : (
              <div className={proChromeClass.shortcutSub}>暂无网卡数据</div>
            )}
          </div>
          {busiest ? (
            <ThinTimeSeries
              bare
              numericAxis
              className={proChromeClass.focusChart}
              title=""
              unit="byteps"
              data={nicTrend}
              legends={[{ label: '吞吐', color: HOST_SERIES_COLOR.netIn }]}
            />
          ) : null}
        </ProFocusCard>
        <ProFocusCard key="process">
          <div className={proChromeClass.shortcutCopy}>
            <FocusShortcutTitle
              label="CPU 占用最高"
              unit={processFocus?.unitLabel}
            />
            {topProcess ? (
              <>
                <div className={proChromeClass.shortcutMain}>{topProcess.labels.process_name || '—'}</div>
                <div className={proChromeClass.shortcutValue} style={{ color: HOST_SERIES_COLOR.cpu }}>
                  {processFocus ? formatFocusHeadline(processFocus, readingOfRow(topProcess, 'process_cpu_usage')) : '--'}
                </div>
                <button type="button" className={proChromeClass.jumpBtn} onClick={() => onJump('process', topProcess.key)}>
                  查看进程
                </button>
              </>
            ) : processLoading ? (
              <ProDashLoading size="small" />
            ) : (
              <div className={proChromeClass.shortcutSub}>暂无进程数据</div>
            )}
          </div>
          {topProcess ? (
            <ThinTimeSeries
              bare
              numericAxis
              className={proChromeClass.focusChart}
              title=""
              unit="percent"
              data={processTrend}
              legends={[{ label: 'CPU', color: HOST_SERIES_COLOR.cpu }]}
            />
          ) : null}
        </ProFocusCard>
      </div>
      </ProSection>

      <ProSection title={hostCategoryText(t, 'viewTrend')}>
      <div className={styles.chartGrid4}>
        <ThinTimeSeries
          title={hostCategoryText(t, 'cpuUtilization')}
          loading={chartLoading(['cpu_usage_total'], cpuTrend.length > 0)}
          unit="percent"
          data={cpuTrend}
          legends={[CPU_SERIES]}
        />
        <ThinTimeSeries
          title={hostCategoryText(t, 'memoryUtilization')}
          loading={chartLoading(['mem_used_percent', 'mem_available', 'mem_total'], memTrend.length > 0)}
          unit="percent"
          data={memTrend}
          legends={[MEM_SERIES]}
        />
        <ThinTimeSeries
          title={hostCategoryText(t, 'diskWeightedUsage')}
          hint="总使用率 = 100% × 各挂载已用之和 / 总量之和。概览 KPI 与告警色点用最满挂载，不是这个合计。"
          loading={diskLoading && diskUsageTrend.length === 0}
          unit="percent"
          emptyText="暂无挂载数据"
          data={diskUsageTrend}
          legends={[DISK_TOTAL_SERIES]}
        />
        <ThinTimeSeries
          title="网卡合计"
          hint="本机全部网卡入站与出站吞吐之和；与「吞吐最高网卡」不同。"
          loading={chartLoading(['net_bytes_recv_rate', 'net_bytes_sent_rate'], netTrend.length > 0)}
          unit="byteps"
          data={netTrend}
          legends={[
            { label: '入', color: HOST_SERIES_COLOR.netIn, reading: formatUnit(netIn, 'byteps') },
            { label: '出', color: HOST_SERIES_COLOR.netOut, reading: formatUnit(netOut, 'byteps') }
          ]}
        />
      </div>
      </ProSection>
    </>
  );
}
