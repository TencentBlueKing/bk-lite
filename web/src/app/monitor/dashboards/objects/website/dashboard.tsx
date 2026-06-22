'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import {
  HorizontalBarPanel,
  RingChartPanel,
  TrendChartPanel
} from '../../shared/widgets';
import { WEBSITE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['探测成功率', '异常状态码', '平均响应时间', '可用节点(2xx)', '平均内容长度'];
const PRIMARY_CHART_TITLES = ['探测成功率趋势', '响应时间趋势', '内容长度趋势'];
const RING_TITLES = ['可用性分布'];
const BAR_TITLES = ['状态码分布'];

export default function WebsiteDashboardPage() {
  const dashboard = useSimpleDashboardData(WEBSITE_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  const [successChart, responseChart, contentChart] = charts;
  const [availabilityRing] = rings;
  const [statusCodeBar] = bars;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>性能趋势与分布</div>
          <FlexiblePanelSection styles={styles}>
            {availabilityRing ? (
              <RingChartPanel
                key={availabilityRing.panel.title}
                title={availabilityRing.panel.title}
                subtitle={availabilityRing.panel.subtitle}
                guide={availabilityRing.panel.guide}
                data={availabilityRing.data}
                centerValue={availabilityRing.centerValue}
                centerCaption={availabilityRing.panel.centerCaption}
                isEmpty={availabilityRing.isEmpty}
                className={`${styles.span4} ${styles.compactStatusRing}`}
                styles={styles}
              />
            ) : null}
            {successChart ? (
              <TrendChartPanel
                key={successChart.chart.title}
                title={successChart.chart.title}
                subtitle={successChart.chart.subtitle}
                guide={successChart.chart.guide}
                legends={successChart.legends}
                data={successChart.data}
                metric={successChart.metric}
                unit={successChart.unit}
                loading={dashboard.loading}
                seriesStyles={successChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {responseChart ? (
              <TrendChartPanel
                key={responseChart.chart.title}
                title={responseChart.chart.title}
                subtitle={responseChart.chart.subtitle}
                guide={responseChart.chart.guide}
                legends={responseChart.legends}
                data={responseChart.data}
                metric={responseChart.metric}
                unit={responseChart.unit}
                loading={dashboard.loading}
                seriesStyles={responseChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {statusCodeBar ? (
              <HorizontalBarPanel
                key={statusCodeBar.panel.title}
                title={statusCodeBar.panel.title}
                subtitle={statusCodeBar.panel.subtitle}
                guide={statusCodeBar.panel.guide}
                items={statusCodeBar.items}
                className={styles.span6}
                styles={styles}
              />
            ) : null}
            {contentChart ? (
              <TrendChartPanel
                key={contentChart.chart.title}
                title={contentChart.chart.title}
                subtitle={contentChart.chart.subtitle}
                guide={contentChart.chart.guide}
                legends={contentChart.legends}
                data={contentChart.data}
                metric={contentChart.metric}
                unit={contentChart.unit}
                loading={dashboard.loading}
                seriesStyles={contentChart.seriesStyles}
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
