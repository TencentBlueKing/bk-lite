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
import { LOADBALANCE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

// 所有负载均衡品牌都采集 CPU / 连接 / 接口流量 / 运行时长，故健康面板恒显示。
// 内存（个别型号无 SNMP 指标）与连接（个别型号无计数）取不到时对应卡片显示「--」、趋势显示空。
const KPI_TITLES = ['运行时长', 'CPU 使用率', '内存使用率', '当前连接', '入向总流量'];
const CHART_TITLES = ['CPU 与内存使用率趋势', '设备收发流量趋势', '当前连接趋势'];

export default function LoadbalanceDashboardPage() {
  const dashboard = useSimpleDashboardData(LOADBALANCE_DASHBOARD_CONFIG);

  const idText =
    (dashboard.idValues?.length ? dashboard.idValues.join('_') : '') ||
    String(dashboard.instanceId ?? '');
  const resolved = resolveCapability('loadbalance', idText);

  const filteredCards = useFilteredSummaryCards(dashboard.summaryCards, KPI_TITLES);
  // 品牌命中时按"矩阵×数据"门控卡片（不支持→剔除；支持但无数据→保留显示 --）；未命中不动。
  const summaryCards = resolved.matched
    ? filteredCards.filter((c) =>
      isMetricVisible(
        resolved,
        'loadbalance',
        c.card?.metric,
        Array.isArray(c.trendData) && c.trendData.length > 0
      )
    )
    : filteredCards;
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const cpuMemChart = charts.find((c) => c?.chart.title === 'CPU 与内存使用率趋势');
  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');
  const connChart = charts.find((c) => c?.chart.title === '当前连接趋势');

  const renderTrend = (chart: (typeof charts)[number], className: string) =>
    chart && isMetricVisible(resolved, 'loadbalance', chart.chart.metric, true) ? (
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

          {/* Row 2: 当前连接趋势 span12 */}
          <div className={styles.sectionLabel}>连接</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(connChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
