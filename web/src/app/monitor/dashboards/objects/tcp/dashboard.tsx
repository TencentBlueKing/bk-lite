'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { TCP_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const CHART_TITLES = ['响应时间趋势', '连通成功率趋势'];
const RING_TITLES = ['探测结果分布'];

export default function TcpDashboardPage() {
  const dashboard = useSimpleDashboardData(TCP_DASHBOARD_CONFIG);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [responseChart, successChart] = charts;
  const [resultRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />
          <div className={styles.sectionLabel}>分布与趋势</div>
          <FlexiblePanelSection styles={styles}>
            {resultRing ? (
              <RingChartPanel
                key={resultRing.panel.title}
                title={resultRing.panel.title}
                subtitle={resultRing.panel.subtitle}
                guide={resultRing.panel.guide}
                data={resultRing.data}
                centerValue={resultRing.centerValue}
                centerCaption={resultRing.panel.centerCaption}
                isEmpty={resultRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {successChart ? (
              <TrendChartPanel
                key={successChart.chart.title}
                title={successChart.chart.title}
                subtitle={successChart.chart.subtitle}
                guide={successChart.chart.guide}
                legends={successChart.legends}
                data={successChart.data}
                metric={successChart.metric}
                unit={successChart.unit}
                loading={dashboard.loading}
                seriesStyles={successChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {responseChart ? (
              <TrendChartPanel
                key={responseChart.chart.title}
                title={responseChart.chart.title}
                subtitle={responseChart.chart.subtitle}
                guide={responseChart.chart.guide}
                legends={responseChart.legends}
                data={responseChart.data}
                metric={responseChart.metric}
                unit={responseChart.unit}
                loading={dashboard.loading}
                seriesStyles={responseChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
