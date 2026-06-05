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
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { ACTIVEMQ_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['当前积压', '消费者数', '入队速率', '出队速率'];
const CHART_TITLES = ['消息吞吐趋势', '积压与消费趋势'];
const DETAIL_TITLES = ['Topic 指标详情'];

export default function ActiveMQDashboardPage() {
  const dashboard = useSimpleDashboardData(ACTIVEMQ_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const details = useFilteredDetailPanels(dashboard.detailPanels, DETAIL_TITLES);

  const [topicDetail] = details;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          <FlexiblePanelSection styles={styles}>
            {charts.map((chart) => (
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
            ))}
            {topicDetail ? (
              <DetailPanelCard
                key={topicDetail.panel.title}
                detailPanel={topicDetail}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
