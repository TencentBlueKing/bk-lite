'use client';

import React from 'react';
import {
  DashboardShell,
  DetailSection,
  InsightSection,
  KpiSection,
  TrendSection
} from '../common/dashboard-components';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import { STORAGE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

export default function StorageDashboardPage() {
  const dashboard = useSimpleDashboardData(STORAGE_DASHBOARD_CONFIG);
  const idText = [
    ...(dashboard.idValues || []),
    dashboard.instanceId,
    dashboard.resolvedInstanceName
  ].join('_').toLowerCase();
  const brandLabel = idText.includes('infinibox')
    ? 'InfiniBox'
    : idText.includes('pure')
      ? 'Pure FlashArray'
      : 'Storage';

  return (
    <DashboardShell
      dashboard={dashboard}
      brandLabel={brandLabel}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>容量与健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>容量与资源</div>
          <InsightSection
            rings={dashboard.ringPanels}
            bars={dashboard.barPanels}
            ringSpanClass={() => styles.span4}
            barSpanClass={() => styles.span4}
            styles={styles}
          />

          <div className={styles.sectionLabel}>性能趋势</div>
          <TrendSection
            charts={dashboard.chartPanels}
            loading={dashboard.loading}
            onXRangeChange={dashboard.onXRangeChange}
            spanClass={(index) => (index === 2 ? styles.span12 : styles.span6)}
            styles={styles}
          />

          <div className={styles.sectionLabel}>诊断明细</div>
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
