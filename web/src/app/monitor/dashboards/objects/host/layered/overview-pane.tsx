'use client';

import React, { useMemo } from 'react';
import Link from 'next/link';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { HOST_PALETTE } from '../config';
import { latestPreferSignal, maxFinite, pointsToChartData, type EntityTableRow } from '../entity-series';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import { KpiStrip, type KpiCardModel } from './signal-bar';
import ThinTimeSeries from './thin-time-series';
import {
  formatBytesPair,
  formatPercent,
  formatPlain,
  formatUnit,
  latestNumber,
  metricHasPoints,
  percentTone
} from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

interface OverviewPaneProps {
  metrics: Record<string, MetricSeries | undefined>;
  loading: boolean;
  diskRows: EntityTableRow[];
  diskLoading: boolean;
  netRows: EntityTableRow[];
  processRows: EntityTableRow[];
  processReady: boolean;
  alertCount: number | null;
  monitorObjectId?: React.Key;
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

export default function OverviewPane({
  metrics,
  loading,
  diskRows,
  diskLoading,
  netRows,
  processRows,
  processReady,
  alertCount,
  monitorObjectId,
  onJump
}: OverviewPaneProps) {
  const worst = diskRows[0];
  const busiest = netRows[0];
  const topProcess = processRows[0];
  const cpu = latestNumber(metrics.cpu_usage_total);
  const mem = latestNumber(metrics.mem_used_percent);
  const load = latestNumber(metrics.system_load1);
  const cores = latestNumber(metrics.cpu_n);
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
        tone: percentTone(cpu),
        color: HOST_PALETTE.emerald,
        trend: metrics.cpu_usage_total?.viewData || []
      },
      {
        key: 'mem',
        label: '内存',
        value: formatPercent(mem),
        tone: percentTone(mem),
        color: HOST_PALETTE.blue,
        trend: metrics.mem_used_percent?.viewData || []
      }
    ];
    if (showLoad) {
      const hot = load != null && cores != null && cores > 0 && load > cores;
      items.push({
        key: 'load',
        label: 'Load1',
        value: formatPlain(load),
        subtitle: cores != null && cores > 0 ? `· ${Math.round(cores)} 核` : undefined,
        tone: hot ? 'var(--color-warning)' : load == null ? undefined : 'var(--color-success)',
        color: HOST_PALETTE.orange,
        trend: metrics.system_load1?.viewData || []
      });
    }
    items.push({
      key: 'disk',
      label: '磁盘峰值',
      value: diskLoading && diskValue == null ? '--' : formatPercent(diskValue),
      detail: mountName ? `挂载 ${mountName}` : '—',
      tone: percentTone(diskValue),
      color: HOST_PALETTE.orange,
      trend: worst ? pointsToChartData([{ points: worst.series.disk_used_percent || [] }]) : []
    });
    const alertTone = alertCount == null
      ? undefined
      : alertCount > 0
        ? 'var(--color-fail)'
        : 'var(--color-success)';
    items.push({
      key: 'uptime',
      label: '运行时长',
      value: uptime == null ? '--' : formatDuration(uptime),
      tone: uptime == null ? undefined : 'var(--color-success)',
      color: HOST_PALETTE.indigo,
      trend: metrics.system_uptime?.viewData || [],
      flat: true
    });
    items.push({
      key: 'alert',
      label: '告警',
      value: alertCount == null ? '--' : String(alertCount),
      tone: alertTone,
      color: 'var(--color-text-3)',
      flat: alertCount != null,
      extra: typeof monitorObjectId === 'string' || typeof monitorObjectId === 'number' ? (
        <Link className={styles.policyLink} href={`/monitor/event/alert?objId=${monitorObjectId}`}>
          查看策略
        </Link>
      ) : (
        <span className={styles.policyLink}>查看策略</span>
      )
    });
    return items;
  }, [
    alertCount,
    cores,
    cpu,
    diskLoading,
    diskValue,
    load,
    mem,
    metrics.cpu_usage_total?.viewData,
    metrics.mem_used_percent?.viewData,
    metrics.system_load1?.viewData,
    metrics.system_uptime?.viewData,
    monitorObjectId,
    mountName,
    showLoad,
    uptime,
    worst
  ]);

  const netIn = latestNumber(metrics.net_bytes_recv_rate);
  const netOut = latestNumber(metrics.net_bytes_sent_rate);

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>健康概览</div>
      </div>
      <KpiStrip items={cards} />

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>重点关注</div>
      </div>
      <div className={styles.shortcutGrid}>
        {worst ? (
          <div className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>用量最高挂载</div>
            <div className={styles.shortcutMain}>
              {mountName || '—'}
              {' · '}
              <span style={{ color: percentTone(diskCurrent) }}>{formatPercent(diskCurrent)}</span>
            </div>
            <div className={styles.shortcutSub}>
              {formatBytesPair(
                (() => {
                  const total = readingOfRow(worst, 'disk_total') ?? worst.values.disk_total;
                  const used = readingOfRow(worst, 'disk_used');
                  if (used != null) return used;
                  if (total != null && diskCurrent != null) return total * diskCurrent / 100;
                  return worst.values.disk_used ?? null;
                })(),
                readingOfRow(worst, 'disk_total') ?? worst.values.disk_total ?? null
              )}
            </div>
            <button type="button" className={styles.jumpBtn} onClick={() => onJump('disk', worst.key)}>
              查看磁盘
            </button>
          </div>
        ) : null}
        {busiest ? (
          <div className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>流量最高网卡</div>
            <div className={styles.shortcutMain}>{busiest.labels.interface || '—'}</div>
            <div className={styles.shortcutSub}>
              {`入 ${formatUnit(readingOfRow(busiest, 'net_bytes_recv_rate'), 'byteps')}`}
            </div>
            <button type="button" className={styles.jumpBtn} onClick={() => onJump('net', busiest.key)}>
              查看网络
            </button>
          </div>
        ) : null}
        {processReady && topProcess ? (
          <div className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>CPU 占用最高</div>
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
          </div>
        ) : null}
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>本机趋势</div>
      </div>
      <div className={styles.chartGrid4}>
        <ThinTimeSeries
          title="CPU使用率"
          reading={formatPercent(cpu)}
          readingTone={percentTone(cpu)}
          loading={loading}
          unit="percent"
          data={metrics.cpu_usage_total?.viewData || []}
          legends={[{ label: 'CPU', color: HOST_PALETTE.emerald }]}
        />
        <ThinTimeSeries
          title="内存使用率"
          reading={formatPercent(mem)}
          readingTone={percentTone(mem)}
          loading={loading}
          unit="percent"
          data={metrics.mem_used_percent?.viewData || []}
          legends={[{ label: '内存', color: HOST_PALETTE.blue }]}
        />
        <ThinTimeSeries
          title={mountName ? `磁盘使用率 · ${mountName}` : '磁盘使用率'}
          reading={formatPercent(diskCurrent)}
          readingTone={percentTone(diskCurrent)}
          loading={diskLoading}
          unit="percent"
          emptyText="暂无挂载数据"
          data={worst ? pointsToChartData([{ points: worst.series.disk_used_percent || [] }]) : []}
          legends={[{ label: mountName || '使用率', color: HOST_PALETTE.orange }]}
        />
        <ThinTimeSeries
          title="网络吞吐 · 入/出"
          loading={loading}
          unit="byteps"
          data={mergeChartSeries([
            { key: 'in', label: '入', data: metrics.net_bytes_recv_rate?.viewData || [] },
            { key: 'out', label: '出', data: metrics.net_bytes_sent_rate?.viewData || [] }
          ])}
          legends={[
            { label: '入', color: HOST_PALETTE.blue, reading: formatUnit(netIn, 'byteps') },
            { label: '出', color: HOST_PALETTE.cyan, reading: formatUnit(netOut, 'byteps') }
          ]}
        />
      </div>
    </>
  );
}
