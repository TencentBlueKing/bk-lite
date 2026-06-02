'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels
} from '../common/dashboard-components';
import {
  RingChartPanel,
  TrendChartPanel
} from '../../shared/widgets';
import { WEBSITE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const PRIMARY_CHART_TITLES = ['响应时间趋势', '探测成功率趋势', '内容长度趋势'];
const RING_TITLES = ['可用性分布', '状态码分布'];

export default function WebsiteDashboardPage() {
  const dashboard = useSimpleDashboardData(WEBSITE_DASHBOARD_CONFIG);
  const charts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [responseChart, successChart, contentChart] = charts;
  const [availabilityRing, statusCodeRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} styles={styles} />
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
                className={`${styles.span8} ${styles.compactTrend} ${styles.wideTrend}`}
                styles={styles}
              />
            ) : null}
            {statusCodeRing ? (
              <RingChartPanel
                key={statusCodeRing.panel.title}
                title={statusCodeRing.panel.title}
                subtitle={statusCodeRing.panel.subtitle}
                guide={statusCodeRing.panel.guide}
                data={statusCodeRing.data}
                centerValue={statusCodeRing.centerValue}
                centerCaption={statusCodeRing.panel.centerCaption}
                className={`${styles.span4} ${styles.compactStatusRing}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
