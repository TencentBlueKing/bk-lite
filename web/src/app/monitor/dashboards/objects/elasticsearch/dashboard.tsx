'use client';

import React, { useMemo } from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  InsightSection,
  KpiSection,
  TrendSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { ClusterHealthCard } from './cluster-health-card';
import { ELASTICSEARCH_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const HEALTH_CARD_TITLE = '集群健康状态';
const SUMMARY_TITLES = ['未分配分片', '主分片分配率', '节点可用磁盘', 'JVM 堆使用率'];
const PRIMARY_CHART_TITLES = ['线程池队列', '熔断器触发', 'HTTP 新建连接'];
const SECONDARY_CHART_TITLES = ['资源使用率', 'GC 耗时趋势'];
const RING_TITLES = ['JVM 堆内存分布', '分片状态分布'];
const BAR_TITLES = ['线程池压力', '熔断器热点'];

export default function ElasticsearchDashboardPage() {
  const dashboard = useSimpleDashboardData(ELASTICSEARCH_DASHBOARD_CONFIG);

  const healthCard = useMemo(
    () => dashboard.summaryCards.find((c) => c.card.title === HEALTH_CARD_TITLE),
    [dashboard.summaryCards]
  );
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection
            dashboard={dashboard}
            summaryCards={summaryCards}
            extraCards={healthCard ? <ClusterHealthCard prepared={healthCard} styles={styles} /> : undefined}
            kpiCols={6}
            styles={styles}
          />
          <TrendSection charts={primaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
          <InsightSection
            rings={rings}
            bars={bars}
            ringSpanClass={() => styles.span4}
            barSpanClass={() => styles.span6}
            styles={styles}
          />
          <TrendSection
            charts={secondaryCharts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={(i) => (i === 0 ? styles.span8 : styles.span4)}
            styles={styles}
          />
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
