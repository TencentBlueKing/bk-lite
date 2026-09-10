'use client';

import React from 'react';
import {
  DashboardShell,
  KpiSection,
  SummaryStatCard,
  TrendSection,
  useFilteredChartPanels,
  useFilteredSummaryCards, DashboardSectionLabel } from '../common/dashboard-components';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { KAFKA_DASHBOARD_CONFIG } from './config';
import { KafkaLagRiskTable } from './lag-risk-table';
import styles from './index.module.scss';

const CLUSTER_HEALTH_TITLES = [
  '探针状态',
  'Broker 数',
  'Topic 数',
  'Topic 分区数',
];
const CONSUMER_RISK_TITLES = [
  '不同步分区数',
  '最大消费者 Lag',
  '异常 Lag 分区数',
  '未提交 Offset 分区数',
];
const CHART_TITLES = ['消费者 Lag 趋势', '分区副本健康趋势'];

function KpiCardGrid({
  cards,
  styles: localStyles,
}: {
  cards: ReturnType<typeof useFilteredSummaryCards>;
  styles: Record<string, string>;
}) {
  if (!cards.length) return null;
  const cols = Math.min(cards.length, 6);
  return (
    <section
      className={localStyles.kpiGrid}
      style={{ '--kpi-cols': cols } as React.CSSProperties}
    >
      {cards.map((summaryCard) => (
        <SummaryStatCard
          key={summaryCard.card.title}
          summaryCard={summaryCard}
          styles={localStyles}
        />
      ))}
    </section>
  );
}

export default function KafkaDashboardPage() {
  const dashboard = useSimpleDashboardData(KAFKA_DASHBOARD_CONFIG);
  const clusterHealthCards = useFilteredSummaryCards(dashboard.summaryCards, CLUSTER_HEALTH_TITLES);
  const consumerRiskCards = useFilteredSummaryCards(dashboard.summaryCards, CONSUMER_RISK_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={(
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection
            dashboard={dashboard}
            summaryCards={clusterHealthCards}
            styles={styles}
          />

          {consumerRiskCards.length > 0 ? (
            <>
              <DashboardSectionLabel styles={styles}>风险信号</DashboardSectionLabel>
              <KpiCardGrid cards={consumerRiskCards} styles={styles} />
            </>
          ) : null}

          <DashboardSectionLabel styles={styles}>关键趋势</DashboardSectionLabel>
          <TrendSection
            charts={charts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => styles.span6}
            styles={styles}
          />

          <DashboardSectionLabel styles={styles}>Lag 排行</DashboardSectionLabel>
          <KafkaLagRiskTable dashboard={dashboard} styles={styles} />
        </>
      )}
    />
  );
}
