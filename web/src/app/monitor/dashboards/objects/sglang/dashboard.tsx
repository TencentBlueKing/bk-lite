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
import { SGLANG_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = [
  '运行中请求数',
  '排队请求数',
  'Token 用量',
  '缓存命中率',
  '生成吞吐'
];
const CHART_TITLES = ['请求队列趋势', 'Token 吞吐趋势', 'TTFT 多分位', 'E2E 多分位'];
const RING_TITLES = ['请求队列分布'];

export default function SglangDashboardPage() {
  const dashboard = useSimpleDashboardData(SGLANG_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

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

  const [queueTrend, tokenTrend, ttftTrend, e2eTrend] = charts;
  const [queueRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>队列与吞吐</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(queueTrend, styles.span8)}
            {queueRing ? (
              <RingChartPanel
                key={queueRing.panel.title}
                title={queueRing.panel.title}
                subtitle={queueRing.panel.subtitle}
                guide={queueRing.panel.guide}
                data={queueRing.data}
                centerValue={queueRing.centerValue}
                centerCaption={queueRing.panel.centerCaption}
                isEmpty={queueRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {renderChart(tokenTrend, styles.span12)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>时延多分位</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(ttftTrend, styles.span6)}
            {renderChart(e2eTrend, styles.span6)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
