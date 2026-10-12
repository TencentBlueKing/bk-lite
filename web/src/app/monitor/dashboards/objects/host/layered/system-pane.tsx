'use client';

import React, { useMemo } from 'react';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { HOST_PALETTE } from '../config';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import ThinTimeSeries from './thin-time-series';
import {
  deriveRatioPercent,
  formatPercent,
  formatPlain,
  latestNumber,
  metricHasPoints,
  numericValue
} from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const CPU_BREAKDOWN = [
  { key: 'cpu_usage_user_total', label: 'user', color: HOST_PALETTE.emerald },
  { key: 'cpu_usage_system_total', label: 'system', color: HOST_PALETTE.neutral },
  { key: 'cpu_usage_iowait_total', label: 'iowait', color: HOST_PALETTE.orange }
];

const LOAD_SERIES = [
  { key: 'system_load1', label: 'load1', color: HOST_PALETTE.orange },
  { key: 'system_load5', label: 'load5', color: HOST_PALETTE.blue },
  { key: 'system_load15', label: 'load15', color: HOST_PALETTE.cyan }
];

export default function SystemPane({
  metrics,
  loading
}: {
  metrics: Record<string, MetricSeries | undefined>;
  loading: boolean;
}) {
  const breakdown = CPU_BREAKDOWN.filter((item) => metricHasPoints(metrics[item.key]));
  const cpuItems = breakdown.length
    ? breakdown
    : metricHasPoints(metrics.cpu_usage_total)
      ? [{ key: 'cpu_usage_total', label: 'CPU', color: HOST_PALETTE.blue }]
      : [];
  const loadItems = LOAD_SERIES.filter((item) => metricHasPoints(metrics[item.key]));
  const available = useMemo(
    () => deriveRatioPercent(metrics.mem_available?.viewData, metrics.mem_total?.viewData),
    [metrics.mem_available?.viewData, metrics.mem_total?.viewData]
  );
  const memItems = [
    ...(metricHasPoints(metrics.mem_used_percent)
      ? [{ key: 'used', label: '已用', color: HOST_PALETTE.blue, data: metrics.mem_used_percent?.viewData || [] }]
      : []),
    ...(available.length
      ? [{ key: 'available', label: '可用', color: HOST_PALETTE.emerald, data: available }]
      : [])
  ];
  const load = latestNumber(metrics.system_load1);
  const cores = latestNumber(metrics.cpu_n);
  const used = latestNumber(metrics.mem_used_percent);
  const availLatest = available.length ? numericValue(available[available.length - 1]) : null;
  const charts = [
    <ThinTimeSeries
      key="cpu"
      title={breakdown.length ? 'CPU 使用（user/system/iowait）' : 'CPU 使用率'}
      loading={loading}
      unit="percent"
      data={mergeChartSeries(cpuItems.map((item) => ({
        key: item.key,
        label: item.label,
        data: metrics[item.key]?.viewData || []
      })))}
      legends={cpuItems.map((item) => ({ label: item.label, color: item.color }))}
    />,
    loadItems.length ? (
      <ThinTimeSeries
        key="load"
        title="系统负载"
        loading={loading}
        unit="none"
        reading={load == null ? undefined : `${formatPlain(load)}${cores != null && cores > 0 ? ` · ${Math.round(cores)} 核` : ''}`}
        readingTone={load != null && cores != null && cores > 0 && load > cores ? 'var(--color-warning)' : undefined}
        reference={cores != null && cores > 0 ? {
          value: cores,
          label: `核数（${Math.round(cores)}）`,
          color: HOST_PALETTE.orange
        } : null}
        data={mergeChartSeries(loadItems.map((item) => ({
          key: item.key,
          label: item.label,
          data: metrics[item.key]?.viewData || []
        })))}
        legends={loadItems.map((item) => ({ label: item.label, color: item.color }))}
      />
    ) : null,
    <ThinTimeSeries
      key="mem"
      title="内存"
      loading={loading}
      unit="percent"
      reading={[
        used == null ? null : `已用 ${formatPercent(used)}`,
        availLatest == null ? null : `可用 ${formatPercent(availLatest)}`
      ].filter(Boolean).join(' · ') || undefined}
      data={mergeChartSeries(memItems.map((item) => ({
        key: item.key,
        label: item.label,
        data: item.data
      })))}
      legends={memItems.map((item) => ({ label: item.label, color: item.color }))}
    />
  ].filter(Boolean);
  const gridClass = charts.length >= 3 ? styles.chartGrid3 : charts.length === 2 ? styles.chartGrid2 : styles.chartGrid;

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>性能</div>
      </div>
      <div className={gridClass}>{charts}</div>
    </>
  );
}
