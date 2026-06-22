'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  KpiSection,
  TrendSection,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { ACTIVEMQ_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['当前积压', '净流入速率', '入队速率', '出队速率', '消费者数'];
const THROUGHPUT_CHART_TITLES = ['消息吞吐趋势', '入出队总量趋势'];
const QUEUE_CHART_TITLES = ['当前积压趋势', '消费者数趋势'];

export default function ActiveMQDashboardPage() {
  const dashboard = useSimpleDashboardData(ACTIVEMQ_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const throughputCharts = useFilteredChartPanels(dashboard.chartPanels, THROUGHPUT_CHART_TITLES);
  const queueCharts = useFilteredChartPanels(dashboard.chartPanels, QUEUE_CHART_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>消息吞吐</div>
          <TrendSection charts={throughputCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <div className={styles.sectionLabel}>积压与消费</div>
          <TrendSection charts={queueCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
        </>
      }
    />
  );
}
