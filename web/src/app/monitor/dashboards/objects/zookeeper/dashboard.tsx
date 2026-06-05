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
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { ZOOKEEPER_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['存活连接数', 'Outstanding 请求', '平均延迟', 'Fsync 风险', 'FD 使用率'];
const CHART_TITLES = ['包收发速率趋势', '请求延迟趋势', '连接数趋势', 'Outstanding 请求趋势', '数据对象趋势'];
const RING_TITLES = ['文件描述符分布'];
const BAR_TITLES = ['Fsync 超阈快照'];
const DETAIL_TITLES = ['Zookeeper 详情'];

export default function ZookeeperDashboardPage() {
  const dashboard = useSimpleDashboardData(ZOOKEEPER_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [packetChart, latencyChart, connectionChart, outstandingChart, objectChart] = charts;
  const [fdRing] = rings;
  const [fsyncBar] = bars;
  const [zkDetail] = details;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          {/* Row 1: packet rate (span6) + latency (span6) = 12 */}
          <FlexiblePanelSection styles={styles}>
            {[packetChart, latencyChart].map((chart) => chart ? (
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
          </FlexiblePanelSection>

          {/* Row 2: connection trend (span4) + outstanding trend (span4) + data-object trend (span4) = 12 */}
          <FlexiblePanelSection styles={styles}>
            {[connectionChart, outstandingChart, objectChart].map((chart) => chart ? (
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
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null)}
          </FlexiblePanelSection>

          {/* Row 3: FD ring (span4) + Fsync bar (span4) + detail (span4) = 12 */}
          <FlexiblePanelSection styles={styles}>
            {fdRing ? (
              <RingChartPanel
                key={fdRing.panel.title}
                title={fdRing.panel.title}
                subtitle={fdRing.panel.subtitle}
                guide={fdRing.panel.guide}
                data={fdRing.data}
                centerValue={fdRing.centerValue}
                centerCaption={fdRing.panel.centerCaption}
                isEmpty={fdRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {fsyncBar ? (
              <HorizontalBarPanel
                key={fsyncBar.panel.title}
                title={fsyncBar.panel.title}
                subtitle={fsyncBar.panel.subtitle}
                guide={fsyncBar.panel.guide}
                items={fsyncBar.items}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {zkDetail ? (
              <DetailPanelCard
                key={zkDetail.panel.title}
                detailPanel={zkDetail}
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
