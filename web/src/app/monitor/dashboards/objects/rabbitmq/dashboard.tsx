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
import { RABBITMQ_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['运行时长', '节点健康', '内存使用率', '未确认占比', '消息积压'];
const CHART_TITLES = ['内存压力趋势', '消息流转趋势', '句柄资源趋势', '节点负载趋势'];
const RING_TITLES = ['节点内存分布'];
const DETAIL_TITLES = ['队列与资源详情'];

export default function RabbitMQDashboardPage() {
  const dashboard = useSimpleDashboardData(RABBITMQ_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [memoryRing] = rings;
  const [resourceDetail] = details;
  const [memoryChart, messageChart, handleChart, loadChart] = charts;

  const renderChart = (chart: typeof charts[number], spanClass: string) =>
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

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          {/* R1: 内存分布环 span4 + 内存压力趋势 span8 = 12 —— 环图配同主题折线,消除中部留白 */}
          <div className={styles.sectionLabel}>内存与压力</div>
          <FlexiblePanelSection styles={styles}>
            {memoryRing ? (
              <RingChartPanel
                key={memoryRing.panel.title}
                title={memoryRing.panel.title}
                subtitle={memoryRing.panel.subtitle}
                guide={memoryRing.panel.guide}
                data={memoryRing.data}
                centerValue={memoryRing.centerValue}
                centerCaption={memoryRing.panel.centerCaption}
                isEmpty={memoryRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {renderChart(memoryChart, styles.span8)}
          </FlexiblePanelSection>

          {/* R2: 消息流转 span6 + 节点负载 span6 = 12 */}
          <div className={styles.sectionLabel}>消息与负载</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(messageChart, styles.span6)}
            {renderChart(loadChart, styles.span6)}
          </FlexiblePanelSection>

          {/* R3: 句柄资源 span6 + 队列与资源详情 span6 = 12 —— 详情配折线 */}
          <div className={styles.sectionLabel}>资源与详情</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(handleChart, styles.span6)}
            {resourceDetail ? (
              <DetailPanelCard
                key={resourceDetail.panel.title}
                detailPanel={resourceDetail}
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
