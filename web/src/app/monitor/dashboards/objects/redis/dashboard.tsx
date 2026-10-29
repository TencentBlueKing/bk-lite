'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  KpiSection,
  TrendSection,
  useFilteredChartPanels,
  useFilteredSummaryCards, DashboardSectionLabel } from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import {
  dashboardModeOptions,
  resolveObjectDashboardMode,
  writeObjectDashboardMode,
  type ObjectDashboardMode
} from '../../shared/utils/pro-dashboard';
import { REDIS_DASHBOARD_CONFIG } from './config';
import RedisArchitectureChip from './layered/architecture-chip';
import RedisCategoryLayout from './layered/category-layout';
import { REDIS_CATEGORY_METRIC_NAMES, REDIS_OVERVIEW_KPI_TITLES } from './layered/overview-metrics';
import styles from './index.module.scss';

const SUMMARY_TITLES: string[] = [...REDIS_OVERVIEW_KPI_TITLES];
const TREND_TITLES = ['内存压力趋势', '缓存命中趋势', '命令吞吐趋势'];
// 键生命周期 + 网络流量 两张折线图占满一行(各 span6)。
const LIFECYCLE_TITLES = ['键生命周期', '网络流量'];

const isRedisDashboardMode = (mode: string): mode is ObjectDashboardMode => (
  mode === 'dashboard' || mode === 'metrics' || mode === 'category'
);

export default function RedisDashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const layout = resolveObjectDashboardMode('redis', new URLSearchParams(searchParams.toString()));
  const dashboard = useSimpleDashboardData(
    REDIS_DASHBOARD_CONFIG,
    layout === 'category'
      ? { metricNames: REDIS_CATEGORY_METRIC_NAMES, reuseLoadedSeries: true }
      : undefined
  );

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const trendCharts = useFilteredChartPanels(dashboard.chartPanels, TREND_TITLES);
  const lifecycleCharts = useFilteredChartPanels(dashboard.chartPanels, LIFECYCLE_TITLES);
  const fragChart = useFilteredChartPanels(dashboard.chartPanels, ['内存碎片'])[0];
  const clientChart = useFilteredChartPanels(dashboard.chartPanels, ['客户端连接趋势'])[0];

  const onLayoutChange = (mode: string) => {
    if (!isRedisDashboardMode(mode) || mode === layout) return;
    const params = writeObjectDashboardMode(new URLSearchParams(searchParams.toString()), mode);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      preserveLayouts
      unifiedChrome
      identityExtra={(
        <RedisArchitectureChip
          metricMap={dashboard.metricSeries}
          instanceKey={String(dashboard.instanceId || '')}
          pendingMetricNames={dashboard.pendingMetricNames}
          booting={dashboard.loading && dashboard.pendingMetricNames.size === 0}
        />
      )}
      viewSwitcher={{
        mode: layout,
        onChange: onLayoutChange,
        control: 'pill',
        options: dashboardModeOptions('redis')
      }}
      categoryContent={(
        <RedisCategoryLayout
          instanceId={dashboard.instanceId}
          monitorObjectId={dashboard.monitorObjectId}
          timeValues={dashboard.timeValues}
          queryTimeRange={dashboard.queryTimeRange}
          loading={dashboard.loading}
          pendingMetricNames={dashboard.pendingMetricNames}
          summaryCards={summaryCards}
          metricMap={dashboard.metricSeries}
        />
      )}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <DashboardSectionLabel styles={styles}>性能与缓存</DashboardSectionLabel>
          <TrendSection charts={trendCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <DashboardSectionLabel styles={styles}>内存与客户端</DashboardSectionLabel>
          <section className={styles.dashboardSection}>
            <div className={styles.sectionGrid}>
              {fragChart && (
                <TrendChartPanel
                  title={fragChart.chart.title}
                  subtitle={fragChart.chart.subtitle}
                  guide={fragChart.chart.guide}
                  legends={fragChart.legends}
                  data={fragChart.data}
                  metric={fragChart.metric}
                  unit={fragChart.unit}
                  loading={dashboard.loading}
                  seriesStyles={fragChart.seriesStyles}
                  onXRangeChange={dashboard.onXRangeChange}
                  className={`${styles.panel} ${styles.span6} ${styles.compactTrend}`}
                  styles={styles}
                />
              )}
              {clientChart && (
                <TrendChartPanel
                  title={clientChart.chart.title}
                  subtitle={clientChart.chart.subtitle}
                  guide={clientChart.chart.guide}
                  legends={clientChart.legends}
                  data={clientChart.data}
                  metric={clientChart.metric}
                  unit={clientChart.unit}
                  loading={dashboard.loading}
                  seriesStyles={clientChart.seriesStyles}
                  onXRangeChange={dashboard.onXRangeChange}
                  className={`${styles.panel} ${styles.span6} ${styles.compactTrend}`}
                  styles={styles}
                />
              )}
            </div>
          </section>

          <DashboardSectionLabel styles={styles}>键生命周期与网络</DashboardSectionLabel>
          <TrendSection charts={lifecycleCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
        </>
      }
    />
  );
}
