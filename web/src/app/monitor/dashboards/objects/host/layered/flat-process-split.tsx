'use client';

import React, { useMemo } from 'react';
import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { HOST_SERIES_COLOR, hostThresholdColor } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import LayeredEntityTable, { type LayeredColumn } from './entity-table';
import TableCsvExportButton from './table-csv-export';
import StatusCountRow, { processStatusView } from './status-count';
import { CardAlertDot, cardAlertClass } from './card-alert';
import ThinTimeSeries from './thin-time-series';
import { resolveMetricLevels, type HostSurfaceAlerts } from './tab-level';
import { formatPercent, formatUnit, latestPreferCount, metricSettled } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const PROCESS_LIST_SCOPE_TIP = '列表仅展示 Telegraf `procstat` 已配置监控的进程；主机上未纳入采集的进程不会出现。';

const numberOrNull = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

const percentColumn = (key: string, title: string): LayeredColumn => ({
  key,
  title,
  unit: 'percent',
  emptyDash: true,
  render: (row) => {
    const value = numberOrNull(row.values[key]);
    if (value == null) return <span className="text-[var(--color-text-3)]">—</span>;
    return (
      <span className="font-medium" style={{ color: hostThresholdColor(value) }}>
        {formatPercent(value)}
      </span>
    );
  }
});

const alivePill = (label: string, tone: 'up' | 'down' | 'unknown') => (
  <span
    className={`inline-flex h-[22px] items-center rounded px-[7px] text-[12px] font-medium leading-none ${
      tone === 'up'
        ? 'bg-[color-mix(in_srgb,var(--color-success)_16%,var(--color-bg))] text-[var(--color-success)]'
        : tone === 'down'
          ? 'bg-[color-mix(in_srgb,var(--color-fail)_14%,var(--color-bg))] text-[var(--color-fail)]'
          : 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]'
    }`}
  >
    {label}
  </span>
);

export default function FlatProcessSplit({
  rows,
  loading,
  selectedKey,
  onSelect,
  metrics,
  metricsLoading = false,
  hostLabel,
  alerts
}: {
  rows: EntityTableRow[];
  loading: boolean;
  selectedKey: string;
  onSelect: (key: string) => void;
  metrics?: Record<string, MetricSeries | undefined>;
  metricsLoading?: boolean;
  hostLabel: string;
  alerts: HostSurfaceAlerts['process'];
}) {
  const { t } = useDashboardText();
  const processListScopeTip = t(
    'monitor.dashboards.text.hostProcessListProcstatScope',
    PROCESS_LIST_SCOPE_TIP
  );
  const sorted = useMemo(
    () => [...rows].sort((left, right) => (right.values.process_cpu_usage ?? -1) - (left.values.process_cpu_usage ?? -1)),
    [rows]
  );
  const selected = sorted.find((row) => row.key === selectedKey) || sorted[0];
  const name = selected?.labels.process_name || '';
  const cpuTrend = useMemo(
    () => pointsToChartData([{ points: selected?.series.process_cpu_usage || [] }]),
    [selected]
  );
  const memTrend = useMemo(
    () => pointsToChartData([{ points: selected?.series.process_mem_usage || [] }]),
    [selected]
  );
  const cpu = numberOrNull(selected?.values.process_cpu_usage);
  const mem = numberOrNull(selected?.values.process_mem_usage);
  const currentLevel = resolveMetricLevels('process', {
    process_cpu_usage: cpu,
    process_mem_usage: mem
  }, ['process_cpu_usage', 'process_mem_usage']);
  // 数值色跟折线序列 token 走，换进程也不改色、不跟行色点。
  const cpuSeries = { label: 'CPU', color: HOST_SERIES_COLOR.cpu, reading: formatPercent(cpu) };
  const memSeries = { label: '内存', color: HOST_SERIES_COLOR.memUsed, reading: formatPercent(mem) };
  const columns = useMemo<LayeredColumn[]>(() => {
    const present = (key: string) => sorted.some((row) => numberOrNull(row.values[key]) != null);
    const next: LayeredColumn[] = [
      { key: 'process_name', title: '进程名', labelKey: 'process_name' }
    ];
    if (present('process_cpu_usage')) next.push(percentColumn('process_cpu_usage', 'CPU'));
    if (present('process_mem_usage')) next.push(percentColumn('process_mem_usage', '内存'));
    if (present('process_memory_rss')) next.push({ key: 'process_memory_rss', title: 'RSS', unit: 'bytes', emptyDash: true });
    if (present('process_num_threads')) next.push({ key: 'process_num_threads', title: '线程', unit: 'counts', emptyDash: true });
    if (present('process_num_fds')) next.push({ key: 'process_num_fds', title: '句柄', unit: 'counts', emptyDash: true });
    if (present('process_alive')) {
      next.push({
        key: 'process_alive',
        title: '存活',
        csvValue: (row) => {
          const value = numberOrNull(row.values.process_alive);
          if (value == null) return '—';
          return value >= 1 ? '是' : '否';
        },
        render: (row) => {
          const value = numberOrNull(row.values.process_alive);
          if (value == null) return alivePill('—', 'unknown');
          return value >= 1 ? alivePill('是', 'up') : alivePill('否', 'down');
        }
      });
    }
    return next;
  }, [sorted]);

  // trend 批次未齐时不把缺序列当成「无数据」；齐了仍缺则显示 --（不可采集），不造假数。
  const statusMetricsSettled = Boolean(
    metrics && (
      metricSettled(metrics.processes_running)
      || metricSettled(metrics.processes_sleeping)
      || metricSettled(metrics.processes_blocked)
      || metricSettled(metrics.processes_zombies)
      || metricSettled(metrics.cpu_usage_user_total)
    )
  );
  const statusPending = !statusMetricsSettled && (metricsLoading || Object.keys(metrics || {}).length > 0);
  const blocked = statusPending ? null : latestPreferCount(metrics?.processes_blocked);
  const zombies = statusPending ? null : latestPreferCount(metrics?.processes_zombies);
  const statusItems = processStatusView({
    blocked,
    zombies,
    running: statusPending ? null : latestPreferCount(metrics?.processes_running),
    sleeping: statusPending ? null : latestPreferCount(metrics?.processes_sleeping)
  }, { settled: !statusPending });

  return (
    <>
      <StatusCountRow
        items={statusItems}
        leafAlerts={{ blocked: alerts.blocked, zombies: alerts.zombies }}
      />
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>趋势</div>
      </div>
      <div className={styles.processTop}>
        <section className={`${classic.panel} ${styles.currentCard} ${cardAlertClass(currentLevel)}`}>
          <CardAlertDot level={currentLevel} />
          <div className={styles.currentKicker}>当前进程</div>
          <div className={styles.currentName}>{name || '—'}</div>
          <div className={styles.currentMetric}>
            CPU
            <b style={{ color: cpuSeries.color }}>{cpuSeries.reading}</b>
          </div>
          <div className={styles.currentMetric}>
            内存
            <b style={{ color: memSeries.color }}>{memSeries.reading}</b>
          </div>
          {numberOrNull(selected?.values.process_memory_rss) != null ? (
            <div className={styles.currentMetric}>
              RSS
              <b>{formatUnit(numberOrNull(selected?.values.process_memory_rss), 'bytes')}</b>
            </div>
          ) : null}
        </section>
        <div className={styles.processTrends}>
          <ThinTimeSeries
            title={name ? `CPU · ${name}` : 'CPU'}
            loading={loading}
            unit="percent"
            data={cpuTrend}
            legends={[{ label: 'CPU', color: cpuSeries.color }]}
          />
          <ThinTimeSeries
            title={name ? `内存 · ${name}` : '内存'}
            loading={loading}
            unit="percent"
            data={memTrend}
            legends={[{ label: '内存', color: memSeries.color }]}
          />
        </div>
      </div>

      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>
          <span className="inline-flex items-center gap-1">
            进程列表
            <Tooltip title={processListScopeTip} styles={{ body: { maxWidth: 360 } }}>
              <QuestionCircleOutlined
                className="cursor-help text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                aria-label={processListScopeTip}
              />
            </Tooltip>
          </span>
        </div>
      </div>
      <LayeredEntityTable
        rows={sorted}
        columns={columns}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        emptyText="暂无进程数据"
        toolbar={<TableCsvExportButton host={hostLabel} slug="processes" columns={columns} rows={sorted} />}
        alertLevel={alerts.list}
        expandedRowRender={(row) => (
          <div className="break-all rounded bg-[var(--color-fill-1)] px-2.5 py-1.5 text-[12px] leading-5 text-[var(--color-text-2)]">
            <span className="text-[var(--color-text-3)]">匹配规则：</span>
            {row.labels.pattern}
          </div>
        )}
        rowExpandable={(row) => row.key === (selected?.key || '') && Boolean(row.labels.pattern)}
      />
    </>
  );
}
