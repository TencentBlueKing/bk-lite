'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { HAPROXY_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['HTTP 请求速率', '平均响应时间'];
const CHART_TITLES = [
  '前端会话',
  '前端请求速率',
  '后端时延拆分',
  'HTTP 状态速率',
  '后端健康与错误',
  '前端流量'
];

export default function HaproxyDashboardPage() {
  const dashboard = useSimpleDashboardData(HAPROXY_DASHBOARD_CONFIG);
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

  const [sessionChart, reqChart, latencyChart, statusChart, healthChart, trafficChart] = charts;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>负载与时延</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(sessionChart, styles.span6)}
            {renderChart(reqChart, styles.span6)}
            {renderChart(latencyChart, styles.span12)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>状态、健康与流量</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(statusChart, styles.span6)}
            {renderChart(healthChart, styles.span6)}
            {renderChart(trafficChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
