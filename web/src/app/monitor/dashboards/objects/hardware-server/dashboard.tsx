'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredSummaryCards,
  DashboardSectionLabel
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { HARDWARE_SERVER_DASHBOARD_CONFIG } from './config';
import { HardwareDimensionTables, extractFirmwareLabel } from './dimension-tables';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['系统健康', '电源状态', 'BMC 健康', '整机功耗', '处理器健康', '内存健康'];
const CHART_TITLES = ['温度', '整机功耗', '风扇转速'];

export default function HardwareServerDashboardPage() {
  const dashboard = useSimpleDashboardData(HARDWARE_SERVER_DASHBOARD_CONFIG);
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const [tempChart, powerChart, fanChart] = charts;
  const firmwareLabel = extractFirmwareLabel(dashboard.chartPanels);

  const renderChart = (chart: (typeof charts)[number], spanClass: string) =>
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
      brandLabel={firmwareLabel}
      styles={styles}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={4} styles={styles} />

          <DashboardSectionLabel styles={styles}>热与功耗</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderChart(tempChart, styles.span6)}
            {renderChart(powerChart, styles.span6)}
          </FlexiblePanelSection>

          <DashboardSectionLabel styles={styles}>风扇</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderChart(fanChart, styles.span6)}
            <HardwareDimensionTables charts={dashboard.chartPanels} styles={styles} include={['fan']} />
          </FlexiblePanelSection>

          <DashboardSectionLabel styles={styles}>电源与网口</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            <HardwareDimensionTables charts={dashboard.chartPanels} styles={styles} include={['psu', 'nic']} />
          </FlexiblePanelSection>

          <DashboardSectionLabel styles={styles}>存储子系统</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            <HardwareDimensionTables charts={dashboard.chartPanels} styles={styles} include={['storage']} />
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
