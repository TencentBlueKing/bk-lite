'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { TrendChartPanel } from '../../shared/widgets';
import { getBrandLabel } from '@/app/monitor/utils/common';
import { resolveCapability, isMetricVisible } from '../../shared/capability-matrix';
import { ROUTER_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

// 所有路由器品牌都采集 CPU / 内存 / 接口流量 / 运行时长，故健康面板恒显示。
// 个别型号取不到的指标对应卡片显示「--」、趋势显示空。
const KPI_TITLES = ['运行时长', 'CPU 使用率', '内存使用率', '入向总流量'];
const CHART_TITLES = ['CPU 与内存使用率趋势', '设备收发流量趋势'];

export default function RouterDashboardPage() {
  const dashboard = useSimpleDashboardData(ROUTER_DASHBOARD_CONFIG);

  const idText =
    (dashboard.idValues?.length ? dashboard.idValues.join('_') : '') ||
    String(dashboard.instanceId ?? '');
  const resolved = resolveCapability('router', idText);

  const filteredCards = useFilteredSummaryCards(dashboard.summaryCards, KPI_TITLES);
  // 品牌命中时按"矩阵×数据"门控卡片（不支持→剔除；支持但无数据→保留显示 --）；未命中不动。
  const summaryCards = resolved.matched
    ? filteredCards.filter((c) =>
      isMetricVisible(
        resolved,
        'router',
        c.card?.metric,
        Array.isArray(c.trendData) && c.trendData.length > 0
      )
    )
    : filteredCards;
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const cpuMemChart = charts.find((c) => c?.chart.title === 'CPU 与内存使用率趋势');
  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');

  const renderTrend = (chart: (typeof charts)[number], className: string) =>
    chart && isMetricVisible(resolved, 'router', chart.chart.metric, true) ? (
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

  // 头部品牌标签：识别到品牌显示品牌名，否则降级「通用 SNMP」。
  const brandLabel = getBrandLabel(idText) ?? '通用 SNMP';

  return (
    <DashboardShell
      dashboard={dashboard}
      brandLabel={brandLabel}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          {/* Row 1: CPU&内存 span6 + 收发流量 span6 */}
          <div className={styles.sectionLabel}>性能趋势</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(cpuMemChart, styles.span6)}
            {renderTrend(trafficChart, styles.span6)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
