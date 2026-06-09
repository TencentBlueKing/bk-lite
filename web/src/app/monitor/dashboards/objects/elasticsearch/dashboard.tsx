'use client';

import React, { useMemo } from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  FlexiblePanelSection,
  KpiSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { ClusterHealthCard } from './cluster-health-card';
import { ELASTICSEARCH_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const HEALTH_CARD_TITLE = '集群健康状态';
const SUMMARY_TITLES = ['未分配分片', '主分片分配率', '节点可用磁盘', 'JVM 堆使用率'];
const PRIMARY_CHART_TITLES = ['线程池队列', '熔断器触发', 'HTTP 新建连接'];
const SECONDARY_CHART_TITLES = ['资源使用率', 'GC 耗时趋势'];
const RING_TITLES = ['JVM 堆内存分布', '分片状态分布'];
const BAR_TITLES = ['线程池压力', '熔断器热点'];

export default function ElasticsearchDashboardPage() {
  const dashboard = useSimpleDashboardData(ELASTICSEARCH_DASHBOARD_CONFIG);

  const healthCard = useMemo(
    () => dashboard.summaryCards.find((c) => c.card.title === HEALTH_CARD_TITLE),
    [dashboard.summaryCards]
  );
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  const [threadQueueChart, breakerTrigChart, httpChart] = primaryCharts;
  const [resourceChart, gcChart] = secondaryCharts;
  const [jvmRing, shardRing] = rings;
  const [threadPoolBar, breakerBar] = bars;

  const renderChart = (chart: typeof primaryCharts[number], spanClass: string) =>
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

  const renderRing = (ring: typeof rings[number], spanClass: string) =>
    ring ? (
      <RingChartPanel
        key={ring.panel.title}
        title={ring.panel.title}
        subtitle={ring.panel.subtitle}
        guide={ring.panel.guide}
        data={ring.data}
        centerValue={ring.centerValue}
        centerCaption={ring.panel.centerCaption}
        isEmpty={ring.isEmpty}
        className={spanClass}
        styles={styles}
      />
    ) : null;

  const renderBar = (bar: typeof bars[number], spanClass: string) =>
    bar ? (
      <HorizontalBarPanel
        key={bar.panel.title}
        title={bar.panel.title}
        subtitle={bar.panel.subtitle}
        guide={bar.panel.guide}
        items={bar.items}
        className={spanClass}
        styles={styles}
      />
    ) : null;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection
            dashboard={dashboard}
            summaryCards={summaryCards}
            extraCards={healthCard ? <ClusterHealthCard prepared={healthCard} styles={styles} /> : undefined}
            kpiCols={6}
            styles={styles}
          />
          {/* 线程池队列 + 熔断器触发 两张折线同行 span6 + span6 = 12 */}
          <FlexiblePanelSection styles={styles}>
            {renderChart(threadQueueChart, styles.span6)}
            {renderChart(breakerTrigChart, styles.span6)}
            {/* 两环图同行 span6 + span6 = 12 */}
            {renderRing(jvmRing, styles.span6)}
            {renderRing(shardRing, styles.span6)}
          </FlexiblePanelSection>
          {/* 线程池压力 + 熔断器热点 + HTTP 新建连接 同行 span4 ×3 = 12 */}
          <FlexiblePanelSection styles={styles}>
            {renderBar(threadPoolBar, styles.span4)}
            {renderBar(breakerBar, styles.span4)}
            {renderChart(httpChart, styles.span4)}
          </FlexiblePanelSection>
          {/* 资源使用率 + GC 耗时趋势 同行 span6 + span6 = 12 */}
          <FlexiblePanelSection styles={styles}>
            {renderChart(resourceChart, styles.span6)}
            {renderChart(gcChart, styles.span6)}
          </FlexiblePanelSection>
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
