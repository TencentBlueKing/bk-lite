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
import { ETCD_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['本机角色', '后端存储使用率', '提案积压', 'WAL fsync P99'];
const CHART_TITLES = ['磁盘时延', '切主与心跳', 'Apply Lag', '提案吞吐', '后端碎片率', 'Put / Delete'];

export default function EtcdDashboardPage() {
  const dashboard = useSimpleDashboardData(ETCD_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const renderChart = (chart: (typeof charts)[number], spanClass: string) =>
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

  const [disk, leader, applyLag, proposal, frag, putDelete] = charts;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={5} styles={styles} />

          <div className={styles.sectionLabel}>磁盘与共识</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(disk, styles.span6)}
            {renderChart(leader, styles.span6)}
            {renderChart(applyLag, styles.span6)}
            {renderChart(proposal, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>容量与写入</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(frag, styles.span6)}
            {renderChart(putDelete, styles.span6)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
