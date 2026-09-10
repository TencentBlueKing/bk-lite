'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredSummaryCards, DashboardSectionLabel } from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { MINIO_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['集群状态', '可用空闲容量', '在线驱动器', 'S3 接收流量'];
const CHART_TITLES = ['空闲容量', '容量使用率', '冗余与成员', 'S3 流量', 'S3 请求队列', '鉴权拒绝'];

export default function MinioDashboardPage() {
  const dashboard = useSimpleDashboardData(MINIO_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const renderChart = (chart: (typeof charts)[number], spanClass: string) =>
    chart ? (
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
        className={`${spanClass} ${styles.compactTrend}`}
        styles={styles}
      />
    ) : null;

  const [freeChart, usedPctChart, redundancyChart, trafficChart, queueChart, authChart] = charts;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={5} styles={styles} />

          <DashboardSectionLabel styles={styles}>容量与冗余</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderChart(freeChart, styles.span6)}
            {renderChart(usedPctChart, styles.span6)}
            {renderChart(redundancyChart, styles.span12)}
          </FlexiblePanelSection>

          <DashboardSectionLabel styles={styles}>S3 服务</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderChart(trafficChart, styles.span6)}
            {renderChart(queueChart, styles.span6)}
            {renderChart(authChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
