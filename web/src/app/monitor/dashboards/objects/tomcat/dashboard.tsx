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
import { TOMCAT_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['线程池利用率', '错误请求速率', '请求处理速率', 'JVM 堆使用率', '最大处理耗时'];
const CHART_TITLES = ['请求错误趋势', '线程池趋势', 'JVM 内存趋势', '发送流量趋势', 'MemoryPool 趋势'];
const RING_TITLES = ['线程池占用分布'];
const DETAIL_TITLES = ['Connector 实时速率详情'];

export default function TomcatDashboardPage() {
  const dashboard = useSimpleDashboardData(TOMCAT_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [requestChart, threadChart, jvmChart, trafficChart, poolChart] = charts;
  const [threadRing] = rings;
  const [rateDetail] = details;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          <FlexiblePanelSection styles={styles}>
            {/* Row 1: two trend charts side-by-side (span6 + span6 = 12) */}
            {requestChart ? (
              <TrendChartPanel
                key={requestChart.chart.title}
                title={requestChart.chart.title}
                subtitle={requestChart.chart.subtitle}
                guide={requestChart.chart.guide}
                legends={requestChart.legends}
                data={requestChart.data}
                metric={requestChart.metric}
                unit={requestChart.unit}
                loading={dashboard.loading}
                seriesStyles={requestChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {threadChart ? (
              <TrendChartPanel
                key={threadChart.chart.title}
                title={threadChart.chart.title}
                subtitle={threadChart.chart.subtitle}
                guide={threadChart.chart.guide}
                legends={threadChart.legends}
                data={threadChart.data}
                metric={threadChart.metric}
                unit={threadChart.unit}
                loading={dashboard.loading}
                seriesStyles={threadChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {/* Row 2: two trend charts side-by-side (span6 + span6 = 12) */}
            {jvmChart ? (
              <TrendChartPanel
                key={jvmChart.chart.title}
                title={jvmChart.chart.title}
                subtitle={jvmChart.chart.subtitle}
                guide={jvmChart.chart.guide}
                legends={jvmChart.legends}
                data={jvmChart.data}
                metric={jvmChart.metric}
                unit={jvmChart.unit}
                loading={dashboard.loading}
                seriesStyles={jvmChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {trafficChart ? (
              <TrendChartPanel
                key={trafficChart.chart.title}
                title={trafficChart.chart.title}
                subtitle={trafficChart.chart.subtitle}
                guide={trafficChart.chart.guide}
                legends={trafficChart.legends}
                data={trafficChart.data}
                metric={trafficChart.metric}
                unit={trafficChart.unit}
                loading={dashboard.loading}
                seriesStyles={trafficChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {/* Footer row: ring(span4) + detail(span4) + memorypool chart(span4) = 12 */}
            {threadRing ? (
              <RingChartPanel
                key={threadRing.panel.title}
                title={threadRing.panel.title}
                subtitle={threadRing.panel.subtitle}
                guide={threadRing.panel.guide}
                data={threadRing.data}
                centerValue={threadRing.centerValue}
                centerCaption={threadRing.panel.centerCaption}
                isEmpty={threadRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {rateDetail ? (
              <DetailPanelCard
                key={rateDetail.panel.title}
                detailPanel={rateDetail}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {poolChart ? (
              <TrendChartPanel
                key={poolChart.chart.title}
                title={poolChart.chart.title}
                subtitle={poolChart.chart.subtitle}
                guide={poolChart.chart.guide}
                legends={poolChart.legends}
                data={poolChart.data}
                metric={poolChart.metric}
                unit={poolChart.unit}
                loading={dashboard.loading}
                seriesStyles={poolChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
