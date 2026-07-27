'use client';

import React from 'react';
import {
  DashboardShell,
  KpiSection,
  TrendSection,
  useFilteredChartPanels,
  useFilteredSummaryCards,
} from '../common/dashboard-components';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { KAFKA_DASHBOARD_CONFIG } from './config';
import { KafkaLagRiskTable } from './lag-risk-table';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['Broker 数', '不同步分区数', '最大消费者 Lag', 'Topic 分区数'];
const CHART_TITLES = ['消费者 Lag 趋势', '分区副本健康趋势'];

export default function KafkaDashboardPage() {
  const dashboard = useSimpleDashboardData(KAFKA_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={(
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>链路风险与趋势</div>
          <TrendSection
            charts={charts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => styles.span6}
            styles={styles}
          />

          <div className={styles.sectionLabel}>风险定位</div>
          <KafkaLagRiskTable dashboard={dashboard} styles={styles} />
        </>
      )}
    />
  );
}
