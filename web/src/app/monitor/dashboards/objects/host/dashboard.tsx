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
import { HOST_DASHBOARD_CONFIG } from './config';
import { HostProcessViewTable } from './process-view-table';
import { HostMetricsSection } from './host-metrics-section';
import styles from './index.module.scss';

const TOP_CHART_TITLES = ['资源使用趋势', '系统负载趋势'];
const NETWORK_CHART_TITLES = ['网络吞吐趋势', '网络错误速率'];
const DISK_PROCESS_CHART_TITLES = ['磁盘吞吐趋势', '进程异常趋势'];
const RING_TITLES = ['CPU 时间分布'];

export default function HostDashboardPage() {
  const dashboard = useSimpleDashboardData(HOST_DASHBOARD_CONFIG);
  const topCharts = useFilteredChartPanels(dashboard.chartPanels, TOP_CHART_TITLES);
  const networkCharts = useFilteredChartPanels(dashboard.chartPanels, NETWORK_CHART_TITLES);
  const diskProcessCharts = useFilteredChartPanels(dashboard.chartPanels, DISK_PROCESS_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [resourceChart, loadChart] = topCharts;
  const [networkChart, networkErrorChart] = networkCharts;
  const [diskChart, processAnomalyChart] = diskProcessCharts;
  const [cpuRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      metricsContent={
        <HostMetricsSection dashboard={dashboard} styles={styles} />
      }
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>性能与分布</div>
          <FlexiblePanelSection styles={styles}>
            {[resourceChart, loadChart].map((chart) => chart ? (
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
                className={`${styles.span4} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null)}
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
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>网络观察</div>
          <FlexiblePanelSection styles={styles}>
            {[networkChart, networkErrorChart].map((chart) => chart ? (
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
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>磁盘与进程</div>
          <FlexiblePanelSection styles={styles}>
            {[diskChart, processAnomalyChart].map((chart) => chart ? (
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
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>进程视图</div>
          <FlexiblePanelSection styles={styles}>
            <HostProcessViewTable dashboard={dashboard} styles={styles} />
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
