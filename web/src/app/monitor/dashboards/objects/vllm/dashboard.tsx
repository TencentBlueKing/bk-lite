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
  '运行中请求数',
  '排队请求数',
  'KV 缓存占用',
  '生成 Token 速率',
  '首 Token 时延 P99'
];
const CHART_TITLES = [
  '请求队列趋势',
  'Token 吞吐趋势',
  'TTFT 多分位',
  'E2E 多分位',
  'ITL 多分位',
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

  const [queueTrend, tokenTrend, ttftTrend, e2eTrend, itlTrend, promptLenTrend, genLenTrend] = charts;
  const [queueRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>推理概览</div>
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
            {renderChart(ttftTrend, styles.span4)}
            {renderChart(e2eTrend, styles.span4)}
            {renderChart(itlTrend, styles.span4)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>Token 长度分布</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(promptLenTrend, styles.span6)}
            {renderChart(genLenTrend, styles.span6)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
