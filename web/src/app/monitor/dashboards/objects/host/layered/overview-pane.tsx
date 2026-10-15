'use client';

import React, { useMemo } from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { hostCategoryText } from './category-copy';
import { HOST_CPU_SERIES_COLOR, HOST_DASHBOARD_CONFIG, HOST_PALETTE } from '../config';
import { latestPreferSignal, maxFinite, pointsToChartData, type EntityTableRow } from '../entity-series';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import EventsRail, { type HostAlertRailEvent } from './events-rail';
import { KpiStrip, type KpiCardModel } from './signal-bar';
import ThinTimeSeries from './thin-time-series';
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

const peakOfRow = (row: EntityTableRow | undefined, key: string) => {
  const fromSeries = maxFinite(row?.series[key]);
  if (fromSeries != null) return fromSeries;
  return latestOfRow(row, key);
};

/** 与本页 CPU / 内存折线共用同一序列色，主值不另写死色。 */
const CPU_SERIES = { label: 'CPU', color: HOST_CPU_SERIES_COLOR };
const MEM_SERIES = { label: '内存', color: HOST_PALETTE.blue };

/** 概览不画 Load 线时，回落到图表配置里 system_load1 的默认序列色。 */
const LOAD1_SERIES_COLOR = HOST_DASHBOARD_CONFIG.charts
  .flatMap((chart) => chart.series)
  .find((series) => series.metric === 'system_load1')?.color
  || HOST_PALETTE.indigo;

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
  onJump
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
  const diskValue = peakOfRow(worst, 'disk_used_percent');
  const diskCurrent = readingOfRow(worst, 'disk_used_percent');
  const mountName = worst?.labels.path || worst?.labels.mount || '';

  const cards = useMemo<KpiCardModel[]>(() => {
    const items: KpiCardModel[] = [
      {
        key: 'cpu',
        label: 'CPU',
        value: formatPercent(cpu),
        tone: CPU_SERIES.color
      },
      {
        key: 'mem',
        label: '内存',
        value: formatPercent(mem),
        tone: MEM_SERIES.color
      }
    ];
    if (showLoad) {
      items.push({
        key: 'load',
        label: hostCategoryText(t, 'loadOneMinute'),
        value: formatPlain(load),
        tone: LOAD1_SERIES_COLOR
      });
    }
    items.push({
      key: 'disk',
      label: hostCategoryText(t, 'diskPeak'),
      hint: hostCategoryText(t, 'diskUtilizationPeak'),
      value: formatPercent(diskValue),
      subtitle: mountName ? `挂载 ${mountName}` : undefined
    });
    const alertTone = alertCount == null
      ? undefined
      : alertCount > 0
        ? 'var(--color-fail)'
        : 'var(--color-success)';
    items.push({
      key: 'uptime',
      label: hostCategoryText(t, 'uptime'),
      value: uptime == null ? '--' : formatDuration(uptime)
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
    diskValue,
    load,
    mem,
    mountName,
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

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>健康概览</div>
      </div>
      <KpiStrip items={cards} />
      <EventsRail events={alertEvents} onFocusAlert={onFocusAlert} />

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>重点关注</div>
      </div>
      <div className={styles.shortcutGrid}>
        <div key="disk" className={`${classic.panel} ${styles.shortcutCard}`}>
          <div className={styles.shortcutLabel}>{hostCategoryText(t, 'busiestMount')}</div>
          {worst ? (
            <>
              <div className={styles.shortcutMain}>
                {mountName || '—'}
                {' · '}
                <span>{formatPercent(diskCurrent)}</span>
              </div>
              <div className={styles.shortcutSub}>
                {(() => {
                  const total = readingOfRow(worst, 'disk_total') ?? worst.values.disk_total ?? null;
                  const used = (() => {
                    const totalBytes = readingOfRow(worst, 'disk_total') ?? worst.values.disk_total;
                    const usedBytes = readingOfRow(worst, 'disk_used');
                    if (usedBytes != null) return usedBytes;
                    if (totalBytes != null && diskCurrent != null) return totalBytes * diskCurrent / 100;
                    return worst.values.disk_used ?? null;
                  })();
                  const usedText = used != null && Number.isFinite(used) ? formatUnit(used, 'bytes') : null;
                  const totalText = total != null && Number.isFinite(total) ? formatUnit(total, 'bytes') : null;
                  if (usedText == null && totalText == null) return '—';
                  return hostCategoryText(t, 'mountUsedOfTotal', {
                    used: usedText ?? '—',
                    total: totalText ?? '—'
                  });
                })()}
              </div>
              <button type="button" className={styles.jumpBtn} onClick={() => onJump('disk', worst.key)}>
                查看磁盘
              </button>
            </>
          ) : (
            <div className={styles.shortcutSub}>{diskLoading ? '加载中' : '暂无挂载数据'}</div>
          )}
        </div>
        <div key="net" className={`${classic.panel} ${styles.shortcutCard}`}>
          <div className={styles.shortcutLabel}>{hostCategoryText(t, 'busiestNic')}</div>
          {busiest ? (
            <>
              <div className={styles.shortcutMain}>{busiest.labels.interface || '—'}</div>
              <div className={styles.shortcutSub}>
                {`该网卡入站 ${formatUnit(readingOfRow(busiest, 'net_bytes_recv_rate'), 'byteps')}`}
              </div>
              <button type="button" className={styles.jumpBtn} onClick={() => onJump('net', busiest.key)}>
                查看网络
              </button>
            </>
          ) : (
            <div className={styles.shortcutSub}>{netLoading ? '加载中' : '暂无网卡数据'}</div>
          )}
        </div>
        {processReady ? (
          <div key="process" className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>CPU 占用最高</div>
            {topProcess ? (
              <>
                <div className={styles.shortcutMain}>
                  {topProcess.labels.process_name || '—'}
                </div>
                <div className={styles.shortcutSub}>
                  {`CPU ${formatPercent(readingOfRow(topProcess, 'process_cpu_usage'))}`}
                  {readingOfRow(topProcess, 'process_mem_usage') != null
                    ? ` · 内存 ${formatPercent(readingOfRow(topProcess, 'process_mem_usage'))}`
                    : ''}
                </div>
                <button type="button" className={styles.jumpBtn} onClick={() => onJump('process', topProcess.key)}>
                  查看进程
                </button>
              </>
            ) : (
              <div className={styles.shortcutSub}>{processLoading ? '加载中' : '暂无进程数据'}</div>
            )}
          </div>
        ) : null}
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>本机趋势</div>
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
          hint={memoryUsage.complementary
            ? '已用占比 = 100% − 可用 / 总量，与性能页同一口径。'
            : undefined}
          loading={loading}
          unit="percent"
          data={memTrend}
          legends={[MEM_SERIES]}
        />
        <ThinTimeSeries
          title={mountName ? `磁盘使用率 · ${mountName}` : '磁盘使用率'}
          loading={diskLoading}
          unit="percent"
          emptyText="暂无挂载数据"
          data={diskTrend}
          legends={[{ label: mountName || '使用率', color: HOST_PALETTE.orange }]}
        />
        <ThinTimeSeries
          title="网络吞吐 · 全部网卡合计"
          hint="主机全部网卡的入站与出站合计，不是上方「吞吐最高网卡」那一块。"
          loading={loading}
          unit="byteps"
          data={netTrend}
          legends={[
            { label: '合计入', color: HOST_PALETTE.blue, reading: formatUnit(netIn, 'byteps') },
            { label: '合计出', color: HOST_PALETTE.cyan, reading: formatUnit(netOut, 'byteps') }
          ]}
        />
      </div>
    </>
  );
}
