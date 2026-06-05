'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailPanelCard,
  FlexiblePanelSection,
  KpiSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredDetailPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, TrendChartPanel } from '../../shared/widgets';
import { DOCKER_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['运行容器数', '停止容器占比', '停止容器数', '容器 CPU 使用率', '容器内存使用率'];
const CHART_TITLES = ['容器资源使用趋势', '网络吞吐趋势', '块设备吞吐趋势'];
const BAR_TITLES = ['容器异常信号'];
const DETAIL_TITLES = ['容器运行详情'];

export default function DockerDashboardPage() {
  const dashboard = useSimpleDashboardData(DOCKER_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [resourceChart, networkChart, blockIoChart] = charts;
  const [anomalyBar] = bars;
  const [containerDetail] = details;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          <FlexiblePanelSection styles={styles}>
            {/* Row 1: resource chart (span6) + network chart (span6) = 12 */}
            {[resourceChart, networkChart].map((chart) => chart ? (
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
            ) : null)}
            {/* Row 2: blockIO chart (span4) + anomaly bar (span4) + detail (span4) = 12 */}
            {blockIoChart ? (
              <TrendChartPanel
                key={blockIoChart.chart.title}
                title={blockIoChart.chart.title}
                subtitle={blockIoChart.chart.subtitle}
                guide={blockIoChart.chart.guide}
                legends={blockIoChart.legends}
                data={blockIoChart.data}
                metric={blockIoChart.metric}
                unit={blockIoChart.unit}
                loading={dashboard.loading}
                seriesStyles={blockIoChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {anomalyBar ? (
              <HorizontalBarPanel
                key={anomalyBar.panel.title}
                title={anomalyBar.panel.title}
                subtitle={anomalyBar.panel.subtitle}
                guide={anomalyBar.panel.guide}
                items={anomalyBar.items}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {containerDetail ? (
              <DetailPanelCard
                key={containerDetail.panel.title}
                detailPanel={containerDetail}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
