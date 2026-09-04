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
import { EXCHANGE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['邮箱投递队列', 'Poison 队列', 'OWA 在线用户', 'AD LDAP 超时', 'OWA 探测'];
const CHART_TITLES = [
  '传输队列全景',
  '客户端访问',
  'HttpProxy 性能',
  '协议与服务发现',
  'AD 目录依赖',
  'Workload 任务',
  'Synthetic 端点延迟',
];
const RING_TITLES = ['传输队列构成'];

export default function ExchangeDashboardPage() {
  const dashboard = useSimpleDashboardData(EXCHANGE_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [
    queueChart,
    clientChart,
    proxyChart,
    protocolChart,
    adChart,
    workloadChart,
    syntheticChart,
  ] = charts;
  const [queueRing] = rings;

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

          <div className={styles.sectionLabel}>Hub Transport 邮件流</div>
          <FlexiblePanelSection styles={styles}>
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
            {renderChart(queueChart, styles.span8)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>客户端访问 (CAS)</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(clientChart, styles.span4)}
            {renderChart(protocolChart, styles.span4)}
            {renderChart(proxyChart, styles.span4)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>Active Directory 依赖</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(adChart, styles.span6)}
            {renderChart(workloadChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>Synthetic 端点探测</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(syntheticChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
