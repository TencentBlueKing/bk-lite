'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredRingPanels
} from '../common/dashboard-components';
import {
  HorizontalBarPanel,
  RingChartPanel,
  TrendChartPanel
} from '../../shared/widgets';
import { HOST_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const TOP_CHART_TITLES = ['资源使用趋势', '系统负载趋势'];
const LOWER_CHART_TITLES = ['网络吞吐趋势', '磁盘吞吐趋势', '进程状态趋势'];
const RING_TITLES = ['CPU 时间分布', '内存占用分布', '进程状态分布'];
const BAR_TITLES = ['主机压力信号'];

export default function HostDashboardPage() {
  const dashboard = useSimpleDashboardData(HOST_DASHBOARD_CONFIG);
  const topCharts = useFilteredChartPanels(dashboard.chartPanels, TOP_CHART_TITLES);
  const lowerCharts = useFilteredChartPanels(dashboard.chartPanels, LOWER_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);
  const [pressureBar] = bars;

  const [resourceChart, loadChart] = topCharts;
  const [networkChart, diskChart, processChart] = lowerCharts;
  const [cpuRing, memoryRing, processRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} styles={styles} />
          <FlexiblePanelSection styles={styles}>
            {resourceChart ? (
              <TrendChartPanel
                key={resourceChart.chart.title}
                title={resourceChart.chart.title}
                subtitle={resourceChart.chart.subtitle}
                guide={resourceChart.chart.guide}
                legends={resourceChart.legends}
                data={resourceChart.data}
                metric={resourceChart.metric}
                unit={resourceChart.unit}
                loading={dashboard.loading}
                seriesStyles={resourceChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {loadChart ? (
              <TrendChartPanel
                key={loadChart.chart.title}
                title={loadChart.chart.title}
                subtitle={loadChart.chart.subtitle}
                guide={loadChart.chart.guide}
                legends={loadChart.legends}
                data={loadChart.data}
                metric={loadChart.metric}
                unit={loadChart.unit}
                loading={dashboard.loading}
                seriesStyles={loadChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {cpuRing ? (
              <RingChartPanel
                key={cpuRing.panel.title}
                title={cpuRing.panel.title}
                subtitle={cpuRing.panel.subtitle}
                guide={cpuRing.panel.guide}
                data={cpuRing.data}
                centerValue={cpuRing.centerValue}
                centerCaption={cpuRing.panel.centerCaption}
                isEmpty={cpuRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
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
            {processRing ? (
              <RingChartPanel
                key={processRing.panel.title}
                title={processRing.panel.title}
                subtitle={processRing.panel.subtitle}
                guide={processRing.panel.guide}
                data={processRing.data}
                centerValue={processRing.centerValue}
                centerCaption={processRing.panel.centerCaption}
                isEmpty={processRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {pressureBar ? (
              <HorizontalBarPanel
                key={pressureBar.panel.title}
                title={pressureBar.panel.title}
                subtitle={pressureBar.panel.subtitle}
                guide={pressureBar.panel.guide}
                items={pressureBar.items}
                className={styles.span12}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
          <FlexiblePanelSection styles={styles}>
            {networkChart ? (
              <TrendChartPanel
                key={networkChart.chart.title}
                title={networkChart.chart.title}
                subtitle={networkChart.chart.subtitle}
                guide={networkChart.chart.guide}
                legends={networkChart.legends}
                data={networkChart.data}
                metric={networkChart.metric}
                unit={networkChart.unit}
                loading={dashboard.loading}
                seriesStyles={networkChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {diskChart ? (
              <TrendChartPanel
                key={diskChart.chart.title}
                title={diskChart.chart.title}
                subtitle={diskChart.chart.subtitle}
                guide={diskChart.chart.guide}
                legends={diskChart.legends}
                data={diskChart.data}
                metric={diskChart.metric}
                unit={diskChart.unit}
                loading={dashboard.loading}
                seriesStyles={diskChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {processChart ? (
              <TrendChartPanel
                key={processChart.chart.title}
                title={processChart.chart.title}
                subtitle={processChart.chart.subtitle}
                guide={processChart.chart.guide}
                legends={processChart.legends}
                data={processChart.data}
                metric={processChart.metric}
                unit={processChart.unit}
                loading={dashboard.loading}
                seriesStyles={processChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span12} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
