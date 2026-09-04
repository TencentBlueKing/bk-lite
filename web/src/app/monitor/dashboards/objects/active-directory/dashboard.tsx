'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards,
} from '../common/dashboard-components';
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { ACTIVE_DIRECTORY_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['LDAP 成功绑定', 'LDAP 客户端会话', '复制积压', 'ATQ 队列延迟', 'LDAP 探测'];
const CHART_TITLES = [
  'LDAP 认证与操作',
  'NTDS 目录服务',
  '复制健康',
  '复制吞吐',
  '会话与 ATQ',
  'LDAP 端点延迟',
];
const RING_TITLES = ['LDAP 操作构成'];

export default function ActiveDirectoryDashboardPage() {
  const dashboard = useSimpleDashboardData(ACTIVE_DIRECTORY_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [ldapChart, ntdsChart, replHealthChart, replThroughputChart, atqChart, probeChart] = charts;
  const [ldapRing] = rings;

  const renderChart = (chart: (typeof charts)[number] | undefined, spanClass: string) =>
    chart ? (
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
        className={`${spanClass} ${styles.compactTrend}`}
        styles={styles}
      />
    ) : null;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>LDAP 认证与目录服务</div>
          <FlexiblePanelSection styles={styles}>
            {ldapRing ? (
              <RingChartPanel
                key={ldapRing.panel.title}
                title={ldapRing.panel.title}
                subtitle={ldapRing.panel.subtitle}
                guide={ldapRing.panel.guide}
                data={ldapRing.data}
                centerValue={ldapRing.centerValue}
                centerCaption={ldapRing.panel.centerCaption}
                isEmpty={ldapRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {renderChart(ldapChart, styles.span8)}
            {renderChart(ntdsChart, styles.span6)}
            {renderChart(atqChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>复制与多域同步 (DRA)</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(replHealthChart, styles.span6)}
            {renderChart(replThroughputChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>Synthetic 端点探测</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(probeChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
