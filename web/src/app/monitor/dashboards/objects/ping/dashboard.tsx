'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  InsightSection,
  KpiSection,
  TrendSection
} from '../common/dashboard-components';
import { PING_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

export default function PingDashboardPage() {
  const dashboard = useSimpleDashboardData(PING_DASHBOARD_CONFIG);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} styles={styles} />
          <TrendSection
            charts={dashboard.chartPanels}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            styles={styles}
          />
          <InsightSection rings={dashboard.ringPanels} bars={dashboard.barPanels} styles={styles} />
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
