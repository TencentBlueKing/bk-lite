'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  KpiSection,
  TrendSection,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { REDIS_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['运行时长', '内存使用率', '缓存命中率', '键驱逐频率', '客户端连接数'];
const TREND_TITLES = ['内存压力趋势', '缓存命中趋势', '命令吞吐趋势'];
// 键生命周期 + 网络流量 两张折线图占满一行(各 span6)。
const LIFECYCLE_TITLES = ['键生命周期', '网络流量'];

export default function RedisDashboardPage() {
  const dashboard = useSimpleDashboardData(REDIS_DASHBOARD_CONFIG);

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const trendCharts = useFilteredChartPanels(dashboard.chartPanels, TREND_TITLES);
  const lifecycleCharts = useFilteredChartPanels(dashboard.chartPanels, LIFECYCLE_TITLES);
  const fragChart = useFilteredChartPanels(dashboard.chartPanels, ['内存碎片'])[0];
  const clientChart = useFilteredChartPanels(dashboard.chartPanels, ['客户端连接趋势'])[0];

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>性能与缓存</div>
          <TrendSection charts={trendCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <div className={styles.sectionLabel}>内存与客户端</div>
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

          <div className={styles.sectionLabel}>键生命周期与网络</div>
          <TrendSection charts={lifecycleCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
        </>
      }
    />
  );
}
