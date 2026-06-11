'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { CONSUL_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['整体健康状态', '通过率', '通过检查数', '警告检查数', '危险检查数'];
const CHART_TITLES = ['健康检查趋势'];
const RING_TITLES = ['健康检查状态分布'];

export default function ConsulDashboardPage() {
  const dashboard = useSimpleDashboardData(CONSUL_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [trendChart] = charts;
  const [distributionRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>趋势与分布</div>
          <FlexiblePanelSection styles={styles}>
            {trendChart ? (
              <TrendChartPanel
                key={trendChart.chart.title}
                title={trendChart.chart.title}
                subtitle={trendChart.chart.subtitle}
                guide={trendChart.chart.guide}
                legends={trendChart.legends}
                data={trendChart.data}
                metric={trendChart.metric}
                unit={trendChart.unit}
                loading={dashboard.loading}
                seriesStyles={trendChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span8} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {distributionRing ? (
              <RingChartPanel
                key={distributionRing.panel.title}
                title={distributionRing.panel.title}
                subtitle={distributionRing.panel.subtitle}
                guide={distributionRing.panel.guide}
                data={distributionRing.data}
                centerValue={distributionRing.centerValue}
                centerCaption={distributionRing.panel.centerCaption}
                isEmpty={distributionRing.isEmpty}
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
