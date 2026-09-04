'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { INFLUXDB_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['Series 数', '写请求速率', '持久化失败'];
const CHART_TITLES = ['读写请求', '写入完整性', 'HTTP 错误', '堆内存趋势'];

export default function InfluxdbDashboardPage() {
  const dashboard = useSimpleDashboardData(INFLUXDB_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const [rwChart, integrityChart, errorChart, heapChart] = charts;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>请求与完整性</div>
          <FlexiblePanelSection styles={styles}>
            {rwChart ? (
              <TrendChartPanel
                key={rwChart.chart.title}
                title={rwChart.chart.title}
                subtitle={rwChart.chart.subtitle}
                guide={rwChart.chart.guide}
                legends={rwChart.legends}
                data={rwChart.data}
                metric={rwChart.metric}
                unit={rwChart.unit}
                loading={dashboard.loading}
                seriesStyles={rwChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {integrityChart ? (
              <TrendChartPanel
                key={integrityChart.chart.title}
                title={integrityChart.chart.title}
                subtitle={integrityChart.chart.subtitle}
                guide={integrityChart.chart.guide}
                legends={integrityChart.legends}
                data={integrityChart.data}
                metric={integrityChart.metric}
                unit={integrityChart.unit}
                loading={dashboard.loading}
                seriesStyles={integrityChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>服务错误与内存</div>
          <FlexiblePanelSection styles={styles}>
            {errorChart ? (
              <TrendChartPanel
                key={errorChart.chart.title}
                title={errorChart.chart.title}
                subtitle={errorChart.chart.subtitle}
                guide={errorChart.chart.guide}
                legends={errorChart.legends}
                data={errorChart.data}
                metric={errorChart.metric}
                unit={errorChart.unit}
                loading={dashboard.loading}
                seriesStyles={errorChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {heapChart ? (
              <TrendChartPanel
                key={heapChart.chart.title}
                title={heapChart.chart.title}
                subtitle={heapChart.chart.subtitle}
                guide={heapChart.chart.guide}
                legends={heapChart.legends}
                data={heapChart.data}
                metric={heapChart.metric}
                unit={heapChart.unit}
                loading={dashboard.loading}
                seriesStyles={heapChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
