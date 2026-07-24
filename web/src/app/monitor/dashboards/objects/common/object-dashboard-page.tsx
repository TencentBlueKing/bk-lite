'use client';

import React from 'react';
import { DashboardShell, DetailSection, KpiSection, TrendSection } from './dashboard-components';
import { useSimpleDashboardData, type SimpleDashboardConfig } from './simple-dashboard-core';

export function ObjectDashboardPage({ config, styles }: { config: SimpleDashboardConfig; styles: Record<string, string> }) {
  const dashboard = useSimpleDashboardData(config);
  return (
    <DashboardShell dashboard={dashboard} styles={styles} dashboardContent={(
      <>
        <div className={styles.sectionLabel}>健康概览</div>
        <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} styles={styles} />
        <div className={styles.sectionLabel}>关键趋势</div>
        <TrendSection charts={dashboard.chartPanels} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
        <div className={styles.sectionLabel}>诊断指标</div>
        <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
      </>
    )} />
  );
}
