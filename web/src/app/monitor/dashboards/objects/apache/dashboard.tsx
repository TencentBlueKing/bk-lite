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
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { APACHE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['服务运行时长', '请求处理速率', '数据传输速率', 'Worker 饱和度', 'CPU Load'];
const CHART_TITLES = ['请求吞吐趋势', 'Worker 状态趋势', 'Scoreboard 状态趋势', '系统负载趋势'];
const RING_TITLES = ['Worker 使用分布'];
const DETAIL_TITLES = ['运行细节'];

export default function ApacheDashboardPage() {
  const dashboard = useSimpleDashboardData(APACHE_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [throughputChart, workerChart, scoreboardChart, loadChart] = charts;
  const [workerRing] = rings;
  const [runtimeDetail] = details;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          {/* Row 1: throughput chart (span6) + worker chart (span6) = 12 */}
          <FlexiblePanelSection styles={styles}>
            {[throughputChart, workerChart].map((chart) => chart ? (
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
            {/* Row 2: scoreboard chart (span6) + load chart (span6) = 12 */}
            {scoreboardChart ? (
              <TrendChartPanel
                key={scoreboardChart.chart.title}
                title={scoreboardChart.chart.title}
                subtitle={scoreboardChart.chart.subtitle}
                guide={scoreboardChart.chart.guide}
                legends={scoreboardChart.legends}
                data={scoreboardChart.data}
                metric={scoreboardChart.metric}
                unit={scoreboardChart.unit}
                loading={dashboard.loading}
                seriesStyles={scoreboardChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {loadChart ? (
              <TrendChartPanel
                key={loadChart.chart.title}
                title={loadChart.chart.title}
                subtitle={loadChart.chart.subtitle}
                guide={loadChart.chart.guide}
                legends={loadChart.legends}
                data={loadChart.data}
                metric={loadChart.metric}
                unit={loadChart.unit}
                loading={dashboard.loading}
                seriesStyles={loadChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
          {/* Row 3: worker ring (span6) + 运行细节详情 (span6) = 12 —— 配对避免单卡留白 */}
          <FlexiblePanelSection styles={styles}>
            {workerRing ? (
              <RingChartPanel
                key={workerRing.panel.title}
                title={workerRing.panel.title}
                subtitle={workerRing.panel.subtitle}
                guide={workerRing.panel.guide}
                data={workerRing.data}
                centerValue={workerRing.centerValue}
                centerCaption={workerRing.panel.centerCaption}
                isEmpty={workerRing.isEmpty}
                className={styles.span6}
                styles={styles}
              />
            ) : null}
            {runtimeDetail ? (
              <DetailPanelCard
                key={runtimeDetail.panel.title}
                detailPanel={runtimeDetail}
                className={styles.span6}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
