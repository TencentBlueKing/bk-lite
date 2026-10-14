'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { hostCategoryText } from './category-copy';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { HOST_PALETTE } from '../config';
import type { EntityTableRow } from '../entity-series';
import { pointsToChartData } from '../entity-series';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import ThinTimeSeries from './thin-time-series';
import { metricBlockPhase, type MetricBlockPhase } from './performance-scope';
import {
  deriveRatioPercent,
  deriveSwapUsedPercentSeries,
  formatBytesPair,
  formatPercent,
  latestNumber,
  metricHasPoints,
  metricSettled,
  numericValue
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
  { key: 'system_load1', label: 'load1', color: HOST_PALETTE.orange },
  { key: 'system_load5', label: 'load5', color: HOST_PALETTE.blue },
  { key: 'system_load15', label: 'load15', color: HOST_PALETTE.cyan }
];

const collectedPoints = (series: MetricSeries | undefined) => (
  series?.query && series.loadState === 'success' ? series.viewData : undefined
);

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

export default function SystemPane({
  metrics,
  pendingMetricNames = EMPTY_PENDING,
  onRetryMetrics,
  coreRows = [],
  coreLoading = false,
  coreFailed = false,
  onRetryCore
}: {
  metrics: Record<string, MetricSeries | undefined>;
  pendingMetricNames?: ReadonlySet<string>;
  onRetryMetrics?: (names: string[]) => void;
  coreRows?: EntityTableRow[];
  coreLoading?: boolean;
  coreFailed?: boolean;
  onRetryCore?: () => void;
}) {
  const { t } = useDashboardText();
  const [selectedCoreKey, setSelectedCoreKey] = useState('');
  const coreIdentity = coreRows.map((row) => row.key).join('|');
  useEffect(() => {
    if (!coreRows.length) {
      setSelectedCoreKey('');
      return;
    }
    setSelectedCoreKey((current) => (
      current && coreRows.some((row) => row.key === current) ? current : coreRows[0].key
    ));
  }, [coreIdentity, coreRows]);

  const breakdown = CPU_BREAKDOWN.filter((item) => metricHasPoints(metrics[item.key]));
  const loadItems = LOAD_SERIES.filter((item) => metricHasPoints(metrics[item.key]));
  const available = useMemo(
    () => deriveRatioPercent(metrics.mem_available?.viewData, metrics.mem_total?.viewData),
    [metrics.mem_available?.viewData, metrics.mem_total?.viewData]
  );
  const swapSeries = useMemo(
    () => deriveSwapUsedPercentSeries(
      collectedPoints(metrics.host_mem_swap_used_bytes),
      collectedPoints(metrics.host_mem_swap_total_bytes),
      collectedPoints(metrics.mem_swap_free)
    ),
    [
      metrics.host_mem_swap_used_bytes,
      metrics.host_mem_swap_total_bytes,
      metrics.mem_swap_free
    ]
  );
  const memItems = [
    ...(metricHasPoints(metrics.mem_used_percent)
      ? [{ key: 'used', label: '已用', color: HOST_PALETTE.blue, data: metrics.mem_used_percent?.viewData || [] }]
      : []),
    ...(available.length
      ? [{ key: 'available', label: '可用', color: HOST_PALETTE.emerald, data: available }]
      : [])
  ];
  const used = latestNumber(metrics.mem_used_percent);
  const availLatest = available.length ? numericValue(available[available.length - 1]) : null;
  const cpuNow = latestNumber(metrics.cpu_usage_total);
  const memNow = latestNumber(metrics.mem_used_percent);
  const availNow = latestNumber(metrics.mem_available);
  const uptimeNow = latestNumber(metrics.system_uptime);
  const swapTotal = latestNumber(metrics.host_mem_swap_total_bytes);
  const swapUsedRaw = latestNumber(metrics.host_mem_swap_used_bytes);
  const swapFree = latestNumber(metrics.mem_swap_free);
  const swapConfigured = swapTotal != null && swapTotal > 0;
  const swapAbsent = metricSettled(metrics.host_mem_swap_total_bytes) && !swapConfigured;
  const swapUsedBytes = swapTotal != null && swapTotal > 0
    ? (swapUsedRaw != null ? swapUsedRaw : swapFree != null ? swapTotal - swapFree : null)
    : null;
  const swapHint = hostCategoryText(t, swapAbsent ? 'swapAbsentHint' : 'swapUsedHint');
  const phaseFor = (names: readonly string[], hasValue: boolean): MetricBlockPhase => (
    metricBlockPhase(names, pendingMetricNames, loadStateOf(metrics, names), hasValue)
  );
  const retry = (names: readonly string[]) => () => onRetryMetrics?.([...names]);
  const cpuNames = ['cpu_usage_total'] as const;
  const memKpiNames = ['mem_used_percent'] as const;
  const availNames = ['mem_available'] as const;
  const swapNames = ['host_mem_swap_used_bytes', 'host_mem_swap_total_bytes', 'mem_swap_free'] as const;
  const uptimeNames = ['system_uptime'] as const;
  const memTrendNames = ['mem_used_percent', 'mem_available', 'mem_total'] as const;
  const loadNames = LOAD_SERIES.map((item) => item.key);
  const breakdownNames = CPU_BREAKDOWN.map((item) => item.key);
  const loadActive = loadNames.some((name) => pendingMetricNames.has(name) || metrics[name]);
  const cpuPhase = phaseFor(cpuNames, metricHasPoints(metrics.cpu_usage_total));
  const memPhase = phaseFor(memTrendNames, memItems.length > 0);
  const loadPhase = phaseFor(loadNames, loadItems.length > 0);
  const breakdownPhase = phaseFor(breakdownNames, breakdown.length > 0);
  const swapPhase = phaseFor(swapNames, swapSeries.length > 0 || swapAbsent);
  const instantCards: Array<{
    key: string;
    label: string;
    value: string;
    unit: string;
    hint?: string;
    names: readonly string[];
    phase: MetricBlockPhase;
  }> = [
    { key: 'cpu', label: 'CPU', names: cpuNames, phase: phaseFor(cpuNames, cpuNow != null), ...splitMetric(cpuNow, 'percent') },
    { key: 'mem', label: '内存', names: memKpiNames, phase: phaseFor(memKpiNames, memNow != null), ...splitMetric(memNow, 'percent') },
    { key: 'avail', label: '可用内存', names: availNames, phase: phaseFor(availNames, availNow != null), ...splitMetric(availNow, 'bytes') },
    {
      key: 'swap',
      label: hostCategoryText(t, 'swapUtilization'),
      names: swapNames,
      phase: phaseFor(swapNames, swapConfigured || swapAbsent),
      value: swapConfigured ? formatBytesPair(swapUsedBytes, swapTotal) : '--',
      unit: '',
      hint: swapHint
    },
    {
      key: 'uptime',
      label: hostCategoryText(t, 'uptime'),
      names: uptimeNames,
      phase: phaseFor(uptimeNames, uptimeNow != null),
      value: uptimeNow == null ? '--' : formatDuration(uptimeNow),
      unit: ''
    }
  ];
  const charts = [
    <ThinTimeSeries
      key="cpu"
      title={hostCategoryText(t, 'cpuUtilization')}
      loading={cpuPhase === 'loading'}
      unit="percent"
      data={metricHasPoints(metrics.cpu_usage_total) ? metrics.cpu_usage_total?.viewData || [] : []}
      emptyText={cpuPhase === 'error' ? '加载失败' : '暂无数据'}
      onRetry={cpuPhase === 'error' ? retry(cpuNames) : undefined}
      legends={[{
        label: 'CPU',
        color: HOST_PALETTE.blue
      }]}
    />,
    <ThinTimeSeries
      key="mem"
      title={hostCategoryText(t, 'memoryUtilization')}
      loading={memPhase === 'loading'}
      unit="percent"
      data={memItems.length ? mergeChartSeries(memItems.map((item) => ({
        key: item.key,
        label: item.label,
        data: item.data
      }))) : []}
      emptyText={memPhase === 'error' ? '加载失败' : '暂无数据'}
      onRetry={memPhase === 'error' ? retry(memTrendNames) : undefined}
      legends={memItems.map((item) => {
        const value = item.key === 'used' ? used : availLatest;
        return {
          label: item.label,
          color: item.color,
          reading: value == null ? undefined : formatPercent(value)
        };
      })}
    />,
    loadActive ? (
      <ThinTimeSeries
        key="load"
        title="系统负载"
        loading={loadPhase === 'loading'}
        unit="none"
        data={loadItems.length ? mergeChartSeries(loadItems.map((item) => ({
          key: item.key,
          label: item.label,
          data: metrics[item.key]?.viewData || []
        }))) : []}
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
  const selectedCore = coreRows.find((row) => row.key === selectedCoreKey) || coreRows[0];
  const selectedCoreName = selectedCore?.labels.cpu || '';
  const selectedCoreAvg = selectedCore?.values.cpu_usage_core_avg;
  const corePeak = coreRows.reduce((peak, row) => Math.max(peak, row.values.cpu_usage_core_avg || 0), 0);
  const detailCards = [
    <ThinTimeSeries
      key="cpu-breakdown"
      title={hostCategoryText(t, 'cpuTimeBreakdown')}
      loading={breakdownPhase === 'loading'}
      unit="percent"
      data={breakdown.length ? mergeChartSeries(breakdown.map((item) => ({
        key: item.key,
        label: item.label,
        data: metrics[item.key]?.viewData || []
      }))) : []}
      emptyText={breakdownPhase === 'error' ? '加载失败' : '暂无数据'}
      onRetry={breakdownPhase === 'error' ? retry(breakdownNames) : undefined}
      legends={breakdown.map((item) => ({
        label: item.label,
        color: item.color
      }))}
    />,
    <ThinTimeSeries
      key="swap"
      title={hostCategoryText(t, 'swapUtilization')}
      hint={swapHint}
      loading={swapPhase === 'loading'}
      unit="percent"
      emptyText={swapPhase === 'error'
        ? '加载失败'
        : swapAbsent
          ? hostCategoryText(t, 'swapAbsentHint')
          : undefined}
      onRetry={swapPhase === 'error' ? retry(swapNames) : undefined}
      data={swapSeries}
      legends={[{
        label: hostCategoryText(t, 'utilization'),
        color: HOST_PALETTE.indigo
      }]}
    />,
    coreLoading ? (
      <section key="cores" className={`${classic.panel} ${styles.chartPanel}`}>
        <div className={styles.chartHead}>
          <div className={styles.chartTitle}>{hostCategoryText(t, 'perCoreCpuUtilization')}</div>
        </div>
        <div className={styles.chartBody}>
          <div className={styles.chartEmpty}>加载中</div>
        </div>
      </section>
    ) : null,
    coreFailed ? (
      <section key="cores-error" className={`${classic.panel} ${styles.chartPanel}`}>
        <div className={styles.chartHead}>
          <div className={styles.chartTitle}>{hostCategoryText(t, 'perCoreCpuUtilization')}</div>
        </div>
        <div className={styles.chartBody}>
          <div className={styles.chartEmpty}>
            加载失败
            <button type="button" className="ml-2 text-[var(--color-primary)]" onClick={onRetryCore}>
              重试
            </button>
          </div>
        </div>
      </section>
    ) : null,
    coreRows.length && selectedCore ? (
      <section key="cores" className={`${classic.panel} ${styles.chartPanel}`}>
        <div className={styles.chartHead}>
          <div className={styles.chartTitleGroup}>
            <div className={styles.chartTitle}>{hostCategoryText(t, 'perCoreCpuUtilization')}</div>
            <div className={styles.chartReading}>{`Top ${coreRows.length} · 选中 ${selectedCoreName}`}</div>
          </div>
        </div>
        <div className="mt-1 grid grid-cols-1 items-start gap-3 min-[960px]:grid-cols-[220px_minmax(0,1fr)]">
          <table className="w-full border-collapse text-[11px]">
            <thead>
              <tr className="text-left font-medium text-[var(--color-text-3)]">
                <th className="border-b border-[var(--color-border)] px-1 py-1">核</th>
                <th className="border-b border-[var(--color-border)] px-1 py-1">{hostCategoryText(t, 'average')}</th>
                <th className="border-b border-[var(--color-border)] px-1 py-1" />
              </tr>
            </thead>
            <tbody>
              {coreRows.map((row) => {
                const active = row.key === selectedCore.key;
                const average = row.values.cpu_usage_core_avg || 0;
                const width = corePeak > 0 ? Math.max(8, Math.round((average / corePeak) * 48)) : 8;
                return (
                  <tr
                    key={row.key}
                    className={active
                      ? 'cursor-pointer bg-[color-mix(in_srgb,var(--color-primary)_14%,transparent)] font-semibold text-[var(--color-primary)]'
                      : 'cursor-pointer text-[var(--color-text-1)]'}
                    onClick={() => setSelectedCoreKey(row.key)}
                  >
                    <td className="border-b border-[var(--color-fill-2)] px-1 py-1 tabular-nums">{row.labels.cpu}</td>
                    <td className="border-b border-[var(--color-fill-2)] px-1 py-1 tabular-nums">{average.toFixed(1)}</td>
                    <td className="border-b border-[var(--color-fill-2)] px-1 py-1">
                      <span
                        className="inline-block h-1 rounded-sm align-middle"
                        style={{
                          width,
                          background: active ? 'var(--color-primary)' : 'var(--color-text-3)'
                        }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <ThinTimeSeries
            bare
            title=""
            loading={false}
            unit="percent"
            data={pointsToChartData([{ points: selectedCore.series.cpu_usage_core || [] }])}
            legends={[{
              label: hostCategoryText(t, 'coreUtilizationNamed', { name: selectedCoreName }),
              color: HOST_PALETTE.blue,
              reading: typeof selectedCoreAvg === 'number' ? formatPercent(selectedCoreAvg) : undefined
            }]}
          />
        </div>
      </section>
    ) : null
  ].filter(Boolean);
  const detailGridClass = detailCards.length >= 3
    ? styles.chartGrid3
    : detailCards.length > 1
      ? styles.chartGrid2
      : 'grid grid-cols-1 gap-3';

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>关键指标</div>
      </div>
      <div className={styles.instantKpiRow}>
        {instantCards.map((card) => (
          <section key={card.key} className={`${classic.panel} ${styles.instantKpi}`}>
            <div className={styles.instantKpiLabel}>
              {card.hint ? (
                <span className="inline-flex items-center gap-1">
                  {card.label}
                  <Tooltip title={card.hint} styles={{ body: { maxWidth: 360 } }}>
                    <QuestionCircleOutlined
                      className="cursor-help text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                      aria-label={card.hint}
                    />
                  </Tooltip>
                </span>
              ) : card.label}
            </div>
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
              <div className={styles.instantKpiValue}>
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
      {detailCards.length ? (
        <>
          <div className={styles.sectionHead}>
            <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>{hostCategoryText(t, 'detailedMetrics')}</div>
          </div>
          <div className={detailGridClass}>{detailCards}</div>
        </>
      ) : null}
    </>
  );
}
