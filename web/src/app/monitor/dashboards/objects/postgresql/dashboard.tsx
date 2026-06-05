'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  InsightSection,
  KpiSection,
  TrendSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { POSTGRESQL_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['活跃连接数', '事务提交速率', '缓存命中率'];
const PRIMARY_CHART_TITLES = ['事务提交与回滚', '缓存与磁盘读', '检查点趋势'];
const SECONDARY_CHART_TITLES = ['缓冲区写入活动', '数据操作速率', '查询行读取趋势'];
const BAR_TITLES = ['异常事件热点', '缓冲区写入来源'];

export default function PostgresqlDashboardPage() {
  const dashboard = useSimpleDashboardData(POSTGRESQL_DASHBOARD_CONFIG);

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          <TrendSection charts={primaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
          <InsightSection
            bars={bars}
            barSpanClass={() => styles.span6}
            styles={styles}
          />
          <TrendSection charts={secondaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
