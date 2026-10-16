'use client';

import React, { useMemo } from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
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
import { KpiStrip, type KpiCardModel } from './signal-bar';
import ThinTimeSeries from './thin-time-series';
import type { HostSurfaceAlerts } from './tab-level';
import {
  formatPercent,
  formatPlain,
  formatUnit,
  latestNumber,
  metricHasPoints,
  primaryChartSeries,
  resolveMemoryUsage
} from './readings';
import classic from '../index.module.scss';
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
  alertsOpen?: boolean;
  onOpenAlerts?: () => void;
  onFocusAlert?: (alertId: string) => void;
  onJump: (tab: 'disk' | 'net' | 'process', key: string) => void;
  alerts: HostSurfaceAlerts['overview'];
}

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
  processReady,
  processLoading = false,
  alertCount,
  alertEvents = [],
  alertsOpen = false,
  onOpenAlerts,
  onFocusAlert,
  onJump,
  alerts
}: OverviewPaneProps) {
  const { t } = useDashboardText();
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
  const uptime = latestNumber(metrics.system_uptime);
  const showLoad = metricHasPoints(metrics.system_load1);
  const diskUsagePoints = useMemo(() => hostDiskUsagePoints(diskRows), [diskRows]);
  const diskUsageLatest = diskUsagePoints.length
    ? diskUsagePoints[diskUsagePoints.length - 1].value
    : null;
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
        alertLevel: alerts.load
      });
    }
    items.push({
      key: 'disk',
      label: hostCategoryText(t, 'diskTotalUsage'),
      value: formatPercent(diskUsageLatest),
      tone: HOST_SERIES_COLOR.diskUsed,
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
    diskUsageLatest,
    load,
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

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>健康概览</div>
      </div>
      <KpiStrip items={cards} />
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'events')}</div>
      </div>
      <EventsRail events={alertEvents} onFocusAlert={onFocusAlert} />

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>重点关注</div>
      </div>
      <div className={styles.shortcutGrid}>
        <div key="disk" className={`${classic.panel} ${styles.shortcutCard}`}>
          <div className={styles.shortcutCopy}>
            <div className={styles.shortcutLabel}>{hostCategoryText(t, 'busiestMount')}</div>
            {worst ? (
              <>
                <div className={styles.shortcutMain}>{mountName || '—'}</div>
                <div className={styles.shortcutValue} style={{ color: HOST_SERIES_COLOR.diskUsed }}>
                  {formatPercent(diskCurrent)}
                </div>
                <button type="button" className={styles.jumpBtn} onClick={() => onJump('disk', worst.key)}>
                  查看磁盘
                </button>
              </>
            ) : (
              <div className={styles.shortcutSub}>{diskLoading ? '加载中' : '暂无挂载数据'}</div>
            )}
          </div>
          {worst ? (
            <ThinTimeSeries
              bare
              className={styles.focusChart}
              title=""
              unit="percent"
              data={diskTrend}
              legends={[{ label: '使用率', color: HOST_SERIES_COLOR.diskUsed }]}
            />
          ) : null}
        </div>
        <div key="net" className={`${classic.panel} ${styles.shortcutCard}`}>
          <div className={styles.shortcutCopy}>
            <div className={styles.shortcutLabel}>{hostCategoryText(t, 'busiestNic')}</div>
            {busiest ? (
              <>
                <div className={styles.shortcutMain}>{busiest.labels.interface || '—'}</div>
                <div className={styles.shortcutValue} style={{ color: HOST_SERIES_COLOR.netIn }}>
                  {formatUnit(nicThroughput, 'byteps')}
                </div>
                <button type="button" className={styles.jumpBtn} onClick={() => onJump('net', busiest.key)}>
                  查看网络
                </button>
              </>
            ) : (
              <div className={styles.shortcutSub}>{netLoading ? '加载中' : '暂无网卡数据'}</div>
            )}
          </div>
          {busiest ? (
            <ThinTimeSeries
              bare
              className={styles.focusChart}
              title=""
              unit="byteps"
              data={nicTrend}
              legends={[{ label: '吞吐', color: HOST_SERIES_COLOR.netIn }]}
            />
          ) : null}
        </div>
        {processReady ? (
          <div key="process" className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutCopy}>
              <div className={styles.shortcutLabel}>CPU 占用最高</div>
              {topProcess ? (
                <>
                  <div className={styles.shortcutMain}>{topProcess.labels.process_name || '—'}</div>
                  <div className={styles.shortcutValue} style={{ color: HOST_SERIES_COLOR.cpu }}>
                    {formatPercent(readingOfRow(topProcess, 'process_cpu_usage'))}
                  </div>
                  <button type="button" className={styles.jumpBtn} onClick={() => onJump('process', topProcess.key)}>
                    查看进程
                  </button>
                </>
              ) : (
                <div className={styles.shortcutSub}>{processLoading ? '加载中' : '暂无进程数据'}</div>
              )}
            </div>
            {topProcess ? (
              <ThinTimeSeries
                bare
                className={styles.focusChart}
                title=""
                unit="percent"
                data={processTrend}
                legends={[{ label: 'CPU', color: HOST_SERIES_COLOR.cpu }]}
              />
            ) : null}
          </div>
        ) : null}
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'viewTrend')}</div>
      </div>
      <div className={styles.chartGrid4}>
        <ThinTimeSeries
          title={hostCategoryText(t, 'cpuUtilization')}
          loading={loading}
          unit="percent"
          data={cpuTrend}
          legends={[CPU_SERIES]}
        />
        <ThinTimeSeries
          title={hostCategoryText(t, 'memoryUtilization')}
          loading={loading}
          unit="percent"
          data={memTrend}
          legends={[MEM_SERIES]}
        />
        <ThinTimeSeries
          title="磁盘使用率"
          hint="总使用率 = 100% × 各挂载已用之和 / 总量之和，与挂载表已用容量同一口径。不是单个挂载。"
          loading={diskLoading}
          unit="percent"
          emptyText="暂无挂载数据"
          data={diskUsageTrend}
          legends={[DISK_TOTAL_SERIES]}
        />
        <ThinTimeSeries
          title="网卡合计"
          hint="本机全部网卡入站与出站吞吐之和；与「吞吐最高网卡」不同。"
          loading={loading}
          unit="byteps"
          data={netTrend}
          legends={[
            { label: '入', color: HOST_SERIES_COLOR.netIn, reading: formatUnit(netIn, 'byteps') },
            { label: '出', color: HOST_SERIES_COLOR.netOut, reading: formatUnit(netOut, 'byteps') }
          ]}
        />
      </div>
    </>
  );
}
