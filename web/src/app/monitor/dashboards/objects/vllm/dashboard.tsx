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
import { VLLM_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = [
  '排队请求数',
  '首 Token 时延 P95',
  'KV 缓存占用',
  'TPOT P95',
  'QPS'
];
const CHART_TITLES = [
  '请求队列趋势',
  '时延拆解',
  'KV 缓存占用',
  'ITL / E2E',
  'Input / Output TPM',
  '输入 Token 长度',
  '输出 Token 长度'
];
const RING_TITLES = ['请求队列分布'];

export default function VllmDashboardPage() {
  const dashboard = useSimpleDashboardData(VLLM_DASHBOARD_CONFIG);
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

  const [queueTrend, latencyBreakdown, kvTrend, tpotTrend, tpmTrend, promptLenTrend, genLenTrend] =
    charts;
  const [queueRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>队列</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />
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
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>TTFT</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(latencyBreakdown, styles.span12)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>KV</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(kvTrend, styles.span12)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>TPOT</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(tpotTrend, styles.span6)}
            {renderChart(tpmTrend, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>单实例</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(promptLenTrend, styles.span6)}
            {renderChart(genLenTrend, styles.span6)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
