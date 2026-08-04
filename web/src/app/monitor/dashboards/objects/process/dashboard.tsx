'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { PROCESS_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const RESOURCE_CHART_TITLES = ['资源使用趋势', '内存 RSS 趋势'];
const CONCURRENCY_CHART_TITLES = ['线程数趋势', '打开文件数趋势'];

export default function ProcessDashboardPage() {
  const dashboard = useSimpleDashboardData(PROCESS_DASHBOARD_CONFIG);
  const resourceCharts = useFilteredChartPanels(dashboard.chartPanels, RESOURCE_CHART_TITLES);
  const concurrencyCharts = useFilteredChartPanels(dashboard.chartPanels, CONCURRENCY_CHART_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>资源趋势</div>
          <FlexiblePanelSection styles={styles}>
            {resourceCharts.map((chart) => (chart ? (
              <TrendChartPanel
                key={chart.chart.title}
                title={chart.chart.title}
                subtitle={chart.chart.subtitle}
                guide={chart.chart.guide}
                legends={chart.legends}
                data={chart.data}
                metric={chart.metric}
                unit={chart.unit}
                loading={dashboard.loading}
                seriesStyles={chart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null))}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>并发与句柄</div>
          <FlexiblePanelSection styles={styles}>
            {concurrencyCharts.map((chart) => (chart ? (
              <TrendChartPanel
                key={chart.chart.title}
                title={chart.chart.title}
                subtitle={chart.chart.subtitle}
                guide={chart.chart.guide}
                legends={chart.legends}
                data={chart.data}
                metric={chart.metric}
                unit={chart.unit}
                loading={dashboard.loading}
                seriesStyles={chart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null))}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
