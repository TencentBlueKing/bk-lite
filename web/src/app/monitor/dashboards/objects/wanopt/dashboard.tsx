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
import { getBrandLabel } from '@/app/monitor/utils/common';
import { resolveCapability, isMetricVisible } from '../../shared/capability-matrix';
import { WANOPT_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const KPI_TITLES = ['运行时长', 'CPU 使用率', '内存使用率', '最高温度', '入向总流量'];
const CHART_TITLES = ['CPU 与内存使用率趋势', '设备收发流量趋势', '机箱温度趋势'];

export default function WanoptDashboardPage() {
  const dashboard = useSimpleDashboardData(WANOPT_DASHBOARD_CONFIG);

  const idText =
    (dashboard.idValues?.length ? dashboard.idValues.join('_') : '') ||
    String(dashboard.instanceId ?? '');
  const resolved = resolveCapability('wanopt', idText);

  const filteredCards = useFilteredSummaryCards(dashboard.summaryCards, KPI_TITLES);
  const summaryCards = resolved.matched
    ? filteredCards.filter((c) =>
      isMetricVisible(
        resolved,
        'wanopt',
        c.card?.metric,
        Array.isArray(c.trendData) && c.trendData.length > 0
      )
    )
    : filteredCards;
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const cpuMemChart = charts.find((c) => c?.chart.title === 'CPU 与内存使用率趋势');
  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');
  const tempChart = charts.find((c) => c?.chart.title === '机箱温度趋势');

  const renderTrend = (chart: (typeof charts)[number], className: string) =>
    chart && isMetricVisible(resolved, 'wanopt', chart.chart.metric, true) ? (
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
        className={`${className} ${styles.compactTrend}`}
        styles={styles}
      />
    ) : null;

  const brandLabel = getBrandLabel(idText) ?? '通用 SNMP';

  return (
    <DashboardShell
      dashboard={dashboard}
      brandLabel={brandLabel}
      styles={styles}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <DashboardSectionLabel styles={styles}>性能趋势</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(cpuMemChart, styles.span6)}
            {renderTrend(trafficChart, styles.span6)}
          </FlexiblePanelSection>

          <DashboardSectionLabel styles={styles}>温度</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(tempChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
