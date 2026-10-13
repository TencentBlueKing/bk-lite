'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards,
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { IIS_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['当前连接', '请求速率', '请求队列', '非运行应用池', '站点探测'];
const CHART_TITLES = [
  '连接与吞吐',
  '请求方法',
  'HTTP 错误',
  '应用程序池',
  '工作进程',
  'HTTP.sys 队列',
  '站点探测延迟',
];
const RING_TITLES = ['在线用户构成'];

export default function IisDashboardPage() {
  const dashboard = useSimpleDashboardData(IIS_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [trafficChart, methodChart, errorChart, poolChart, workerChart, queueChart, probeChart] = charts;
  const [userRing] = rings;

  const renderChart = (chart: (typeof charts)[number] | undefined, spanClass: string) =>
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

          <div className={styles.sectionLabel}>站点流量</div>
          <FlexiblePanelSection styles={styles}>
            {userRing ? (
              <RingChartPanel
                key={userRing.panel.title}
                title={userRing.panel.title}
                subtitle={userRing.panel.subtitle}
                guide={userRing.panel.guide}
                data={userRing.data}
                centerValue={userRing.centerValue}
                centerCaption={userRing.panel.centerCaption}
                isEmpty={userRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {renderChart(trafficChart, styles.span8)}
            {renderChart(methodChart, styles.span6)}
            {renderChart(errorChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>应用程序池与工作进程</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(poolChart, styles.span6)}
            {renderChart(workerChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>HTTP.sys 请求队列</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(queueChart, styles.span12)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>站点探测</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(probeChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
