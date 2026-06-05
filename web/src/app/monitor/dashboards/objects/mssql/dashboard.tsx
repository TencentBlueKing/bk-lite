'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  InsightSection,
  KpiSection,
  TrendSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { MSSQL_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['信号等待占比', '读延迟', '批量请求速率', '缓存命中率', '卷可用空间'];
const PRIMARY_CHART_TITLES = ['等待时间趋势', '请求耗时趋势', '读写延迟'];
const SECONDARY_CHART_TITLES = ['CPU 使用情况', '读写吞吐'];
const RING_TITLES = ['缓存命中分布', '存储空间分布'];
const BAR_TITLES = ['调度器压力', '请求资源消耗'];

export default function MssqlDashboardPage() {
  const dashboard = useSimpleDashboardData(MSSQL_DASHBOARD_CONFIG);

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          <TrendSection charts={primaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
          <InsightSection
            rings={rings}
            bars={bars}
            ringSpanClass={() => styles.span3}
            barSpanClass={() => styles.span3}
            styles={styles}
          />
          <TrendSection
            charts={secondaryCharts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={(i) => (i === 0 ? styles.span8 : styles.span4)}
            styles={styles}
          />
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
