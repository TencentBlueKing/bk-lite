'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { PING_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['平均丢包率', '平均延迟'];
const CHART_TITLES = ['丢包率趋势', '延迟趋势'];
const RING_TITLES = ['结果码分布'];

export default function PingDashboardPage() {
  const dashboard = useSimpleDashboardData(PING_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [lossChart, latencyChart] = charts;
  const [resultRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={3} styles={styles} />
          <div className={styles.sectionLabel}>趋势与归因</div>
          <FlexiblePanelSection styles={styles}>
            {lossChart ? (
              <TrendChartPanel
                key={lossChart.chart.title}
                title={lossChart.chart.title}
                subtitle={lossChart.chart.subtitle}
                guide={lossChart.chart.guide}
                legends={lossChart.legends}
                data={lossChart.data}
                metric={lossChart.metric}
                unit={lossChart.unit}
                loading={dashboard.loading}
                seriesStyles={lossChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {latencyChart ? (
              <TrendChartPanel
                key={latencyChart.chart.title}
                title={latencyChart.chart.title}
                subtitle={latencyChart.chart.subtitle}
                guide={latencyChart.chart.guide}
                legends={latencyChart.legends}
                data={latencyChart.data}
                metric={latencyChart.metric}
                unit={latencyChart.unit}
                loading={dashboard.loading}
                seriesStyles={latencyChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
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
                emptyDescription={resultRing.emptyDescription}
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
