'use client';

import React from 'react';
import { DashboardShell, DetailSection, KpiSection, TrendSection } from './dashboard-components';
import { useSimpleDashboardData, type SimpleDashboardConfig } from './simple-dashboard-core';

interface TrendSectionConfig {
  title: string;
  chartTitles: string[];
}

export function ObjectDashboardPage({
  config,
  styles,
  trendSections
}: {
  config: SimpleDashboardConfig;
  styles: Record<string, string>;
  trendSections?: TrendSectionConfig[];
}) {
  const dashboard = useSimpleDashboardData(config);
  const sections = trendSections || [{ title: '关键趋势', chartTitles: dashboard.chartPanels.map(({ chart }) => chart.title) }];
  return (
    <DashboardShell dashboard={dashboard} styles={styles} dashboardContent={(
      <>
        <div className={styles.sectionLabel}>健康概览</div>
        <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} styles={styles} />
        {sections.map((section) => {
          const charts = dashboard.chartPanels.filter(({ chart }) => section.chartTitles.includes(chart.title));
          if (charts.length === 0) return null;
          return (
            <React.Fragment key={section.title}>
              <div className={styles.sectionLabel}>{section.title}</div>
              <TrendSection charts={charts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />
            </React.Fragment>
          );
        })}
        <div className={styles.sectionLabel}>诊断指标</div>
        <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
      </>
    )} />
  );
}
