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
import { IBMMQ_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['运行时长', '队列管理器状态', '连接数', '内存使用率', '主日志空间'];
// 「消息积压」改为带时间轴的折线图,与内存分布环、资源压力趋势合并到同一行(等分三栏)。
const CHART_TITLES = ['消息积压趋势', '资源压力趋势', '连接趋势', '日志空间趋势', '队列排队趋势'];
const RING_TITLES = ['主机内存分布'];
const DETAIL_TITLES = ['主题与订阅详情'];

export default function IBMMQDashboardPage() {
  const dashboard = useSimpleDashboardData(IBMMQ_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [memoryRing] = rings;
  const [topicDetail] = details;
  const [backlogChart, resourceChart, connChart, logChart, queueChart] = charts;

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

          {/* R1: 消息积压趋势 span4 + 内存分布环 span4 + 资源压力趋势 span4 = 12 */}
          <div className={styles.sectionLabel}>内存与资源</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(backlogChart, styles.span4)}
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
            {renderChart(resourceChart, styles.span4)}
          </FlexiblePanelSection>

          {/* R2: 连接趋势 span6 + 日志空间趋势 span6 = 12 */}
          <div className={styles.sectionLabel}>连接与日志</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(connChart, styles.span6)}
            {renderChart(logChart, styles.span6)}
          </FlexiblePanelSection>

          {/* R3: 队列排队趋势 span6 + 主题与订阅详情 span6 = 12 */}
          <div className={styles.sectionLabel}>队列与主题</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(queueChart, styles.span6)}
            {topicDetail ? (
              <DetailPanelCard
                key={topicDetail.panel.title}
                detailPanel={topicDetail}
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
