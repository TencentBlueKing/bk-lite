'use client';

import React, { useMemo } from 'react';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { HOST_PALETTE } from '../config';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
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

const splitMetric = (value: number | null, unit: MetricUnit) => {
  if (value == null) return { value: '--', unit: '' };
  const formatted = formatMetricValue(value, unit);
  return { value: formatted.value, unit: formatted.unit };
};

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
  const cpuNow = latestNumber(metrics.cpu_usage_total);
  const memNow = latestNumber(metrics.mem_used_percent);
  const availNow = latestNumber(metrics.mem_available);
  const uptimeNow = latestNumber(metrics.system_uptime);
  const swapUsed = latestNumber(metrics.host_mem_swap_used_bytes);
  const swapTotal = latestNumber(metrics.host_mem_swap_total_bytes);
  const swapFree = latestNumber(metrics.mem_swap_free);
  const swapRaw = swapTotal != null && swapTotal > 0
    ? swapUsed != null
      ? (100 * swapUsed) / swapTotal
      : swapFree != null
        ? (100 * (swapTotal - swapFree)) / swapTotal
        : null
    : null;
  const swapNow = swapRaw == null ? null : Math.min(100, Math.max(0, swapRaw));
  const instantCards = [
    { key: 'cpu', label: 'CPU', ...splitMetric(cpuNow, 'percent') },
    { key: 'mem', label: '内存', ...splitMetric(memNow, 'percent') },
    { key: 'avail', label: '可用内存', ...splitMetric(availNow, 'bytes') },
    { key: 'swap', label: '交换已用', ...splitMetric(swapNow, 'percent') },
    {
      key: 'uptime',
      label: '运行时长',
      value: uptimeNow == null ? '--' : formatDuration(uptimeNow),
      unit: ''
    }
  ];
  const loadHot = load != null && cores != null && cores > 0 && load > cores;
  const charts = [
    <ThinTimeSeries
      key="cpu"
      title="CPU使用率"
      loading={loading}
      unit="percent"
      data={mergeChartSeries(cpuItems.map((item) => ({
        key: item.key,
        label: item.label,
        data: metrics[item.key]?.viewData || []
      })))}
      legends={cpuItems.map((item) => {
        const value = latestNumber(metrics[item.key]);
        return {
          label: item.label,
          color: item.color,
          reading: value == null ? undefined : formatPercent(value)
        };
      })}
    />,
    <ThinTimeSeries
      key="mem"
      title="内存使用率"
      loading={loading}
      unit="percent"
      data={mergeChartSeries(memItems.map((item) => ({
        key: item.key,
        label: item.label,
        data: item.data
      })))}
      legends={memItems.map((item) => {
        const value = item.key === 'used' ? used : availLatest;
        return {
          label: item.label,
          color: item.color,
          reading: value == null ? undefined : formatPercent(value)
        };
      })}
    />,
    loadItems.length ? (
      <ThinTimeSeries
        key="load"
        title="系统负载"
        loading={loading}
        unit="none"
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
        legends={loadItems.map((item) => {
          const value = latestNumber(metrics[item.key]);
          return {
            label: item.label,
            color: item.color,
            reading: value == null ? undefined : formatPlain(value),
            readingTone: item.key === 'system_load1' && loadHot ? 'var(--color-warning)' : undefined
          };
        })}
      />
    ) : null
  ].filter(Boolean);
  const gridClass = charts.length >= 3 ? styles.chartGrid3 : charts.length === 2 ? styles.chartGrid2 : styles.chartGrid;

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>关键指标</div>
      </div>
      <div className={styles.instantKpiRow}>
        {instantCards.map((card) => (
          <section key={card.key} className={`${classic.panel} ${styles.instantKpi}`}>
            <div className={styles.instantKpiLabel}>{card.label}</div>
            <div className={styles.instantKpiValue}>
              {card.value}
              {card.unit ? <span className={styles.instantKpiUnit}>{card.unit}</span> : null}
            </div>
          </section>
        ))}
      </div>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>本机趋势</div>
      </div>
      <div className={gridClass}>{charts}</div>
    </>
  );
}
