'use client';

import React, { useMemo } from 'react';
import Link from 'next/link';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { HOST_PALETTE } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import type { MetricSeries } from '../../common/simple-dashboard-core';
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
  const showLoad = metricHasPoints(metrics.system_load1);
  const diskValue = latestOfRow(worst, 'disk_used_percent');
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
        label: 'load1',
        value: formatPlain(load),
        subtitle: cores != null && cores > 0 ? `· ${Math.round(cores)}C` : undefined,
        tone: hot ? 'var(--color-warning)' : load == null ? undefined : 'var(--color-success)',
        color: HOST_PALETTE.orange,
        trend: metrics.system_load1?.viewData || []
      });
    }
    items.push({
      key: 'disk',
      label: '磁盘 MAX',
      value: diskLoading && diskValue == null ? '--' : formatPercent(diskValue),
      detail: mountName || undefined,
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
      key: 'alert',
      label: '告警 · bk-lite',
      value: alertCount == null ? '--' : String(alertCount),
      tone: alertTone,
      color: 'var(--color-text-3)',
      flat: alertCount != null,
      extra: typeof monitorObjectId === 'string' || typeof monitorObjectId === 'number' ? (
        <Link className={styles.policyLink} href={`/monitor/event/alert?objId=${monitorObjectId}`}>
          策略命中 →
        </Link>
      ) : (
        <span className={styles.policyLink}>策略命中 →</span>
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
    monitorObjectId,
    mountName,
    showLoad,
    worst
  ]);

  const netIn = latestNumber(metrics.net_bytes_recv_rate);
  const netOut = latestNumber(metrics.net_bytes_sent_rate);

  return (
    <>
      <KpiStrip items={cards} />
      <div className={styles.sectionHead}>
        <span />
        <div className={styles.hint}>
          {`跳 Tab 预选 · Metrics 固定整机${processReady ? '' : ' · 无 Process 对象'}`}
        </div>
      </div>

      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>关注捷径</div>
      </div>
      <div className={styles.shortcutGrid}>
        {worst ? (
          <div className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>最差磁盘</div>
            <div className={styles.shortcutMain}>
              {mountName || '—'}
              {' · '}
              <span style={{ color: percentTone(diskValue) }}>{formatPercent(diskValue)}</span>
            </div>
            <div className={styles.shortcutSub}>
              {formatBytesPair(worst.values.disk_used, worst.values.disk_total)}
              {diskValue != null && diskValue >= 80 ? ' · used%≥80' : ''}
            </div>
            <button type="button" className={styles.jumpBtn} onClick={() => onJump('disk', worst.key)}>
              → 磁盘
            </button>
          </div>
        ) : null}
        {busiest ? (
          <div className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>最忙网卡</div>
            <div className={styles.shortcutMain}>{busiest.labels.interface || '—'}</div>
            <div className={styles.shortcutSub}>
              {`${formatUnit(latestOfRow(busiest, 'net_bytes_recv_rate'), 'byteps')} in · 只跳 Tab`}
            </div>
            <button type="button" className={styles.jumpBtn} onClick={() => onJump('net', busiest.key)}>
              → 网络
            </button>
          </div>
        ) : null}
        {processReady && topProcess ? (
          <div className={`${classic.panel} ${styles.shortcutCard}`}>
            <div className={styles.shortcutLabel}>Top 进程</div>
            <div className={styles.shortcutMain}>
              {`${topProcess.labels.process_name || '—'} ${formatPercent(latestOfRow(topProcess, 'process_cpu_usage'))}`}
            </div>
            <div className={styles.shortcutSub}>cpu · mem</div>
            <button type="button" className={styles.jumpBtn} onClick={() => onJump('process', topProcess.key)}>
              → 进程
            </button>
          </div>
        ) : null}
      </div>

      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>Metrics · 整机合计（固定）</div>
        <div className={styles.hint}>不跟捷径/表互动</div>
      </div>
      <div className={styles.chartGrid4}>
        <ThinTimeSeries
          title="CPU %"
          reading={formatPercent(cpu)}
          readingTone={percentTone(cpu)}
          loading={loading}
          unit="percent"
          data={metrics.cpu_usage_total?.viewData || []}
          legends={[{ label: 'CPU', color: HOST_PALETTE.emerald }]}
        />
        <ThinTimeSeries
          title="内存 %"
          reading={formatPercent(mem)}
          readingTone={percentTone(mem)}
          loading={loading}
          unit="percent"
          data={metrics.mem_used_percent?.viewData || []}
          legends={[{ label: '内存', color: HOST_PALETTE.blue }]}
        />
        <ThinTimeSeries
          title={mountName ? `磁盘 used% · ${mountName}` : '磁盘 used%'}
          reading={formatPercent(diskValue)}
          readingTone={percentTone(diskValue)}
          loading={diskLoading}
          unit="percent"
          emptyText="当前时间窗没有挂载用量"
          data={worst ? pointsToChartData([{ points: worst.series.disk_used_percent || [] }]) : []}
          legends={[{ label: mountName || 'used%', color: HOST_PALETTE.orange }]}
        />
        <ThinTimeSeries
          title="网络 入+出 · 整机合计"
          reading={`${formatUnit(netIn, 'byteps')} / ${formatUnit(netOut, 'byteps')}`}
          loading={loading}
          unit="byteps"
          data={mergeChartSeries([
            { key: 'in', label: '入', data: metrics.net_bytes_recv_rate?.viewData || [] },
            { key: 'out', label: '出', data: metrics.net_bytes_sent_rate?.viewData || [] }
          ])}
          legends={[
            { label: '入', color: HOST_PALETTE.blue },
            { label: '出', color: HOST_PALETTE.cyan }
          ]}
        />
      </div>
    </>
  );
}
