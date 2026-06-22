'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailPanelCard,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredDetailPanels,
  useFilteredRingPanels
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { PING_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const CHART_TITLES = ['延迟趋势', '丢包率趋势', 'TTL 趋势'];
const DETAIL_TITLES = ['网络探测详情'];
const RING_TITLES = ['连通质量分布'];

export default function PingDashboardPage() {
  const dashboard = useSimpleDashboardData(PING_DASHBOARD_CONFIG);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const detailPanels = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [latencyChart, lossChart, ttlChart] = charts;
  const [qualityRing] = rings;
  const [detailPanel] = detailPanels;

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
            {qualityRing ? (
              <RingChartPanel
                key={qualityRing.panel.title}
                title={qualityRing.panel.title}
                subtitle={qualityRing.panel.subtitle}
                guide={qualityRing.panel.guide}
                data={qualityRing.data}
                centerValue={qualityRing.centerValue}
                centerCaption={qualityRing.panel.centerCaption}
                isEmpty={qualityRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
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
            {detailPanel ? <DetailPanelCard detailPanel={detailPanel} className={styles.span6} styles={styles} /> : null}
            {ttlChart ? (
              <TrendChartPanel
                key={ttlChart.chart.title}
                title={ttlChart.chart.title}
                subtitle={ttlChart.chart.subtitle}
                guide={ttlChart.chart.guide}
                legends={ttlChart.legends}
                data={ttlChart.data}
                metric={ttlChart.metric}
                unit={ttlChart.unit}
                loading={dashboard.loading}
                seriesStyles={ttlChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
