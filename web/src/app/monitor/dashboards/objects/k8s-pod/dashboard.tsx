'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  KpiSection,
  FlexiblePanelSection,
  DetailPanelCard
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { POD_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

export default function K8sPodDashboardPage() {
  const dashboard = useSimpleDashboardData(POD_DASHBOARD_CONFIG);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>Pod 概览</div>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={5} styles={styles} />
          <div className={styles.sectionLabel}>资源趋势</div>
          <FlexiblePanelSection styles={styles}>
            {dashboard.chartPanels.map((chart) => (
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
          </FlexiblePanelSection>
          <div className={styles.sectionLabel}>详情</div>
          <FlexiblePanelSection styles={styles}>
            {dashboard.detailPanels.map((detailPanel) => (
              <DetailPanelCard
                key={detailPanel.panel.title}
                detailPanel={detailPanel}
                className={styles.span4}
                styles={styles}
              />
            ))}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
