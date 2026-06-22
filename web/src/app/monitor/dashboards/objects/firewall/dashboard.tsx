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
import { FIREWALL_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

// 所有防火墙品牌都采集 CPU / 会话或连接 / 接口流量 / 运行时长，故健康面板恒显示。
// 内存（部分型号无 SNMP 指标）与会话（个别型号无计数）取不到时对应卡片显示「--」、趋势显示空。
const KPI_TITLES = ['运行时长', 'CPU 使用率', '内存使用率', '活动会话/连接', '入向总流量'];
const CHART_TITLES = ['CPU 与内存使用率趋势', '设备收发流量趋势', '活动会话/连接趋势'];

export default function FirewallDashboardPage() {
  const dashboard = useSimpleDashboardData(FIREWALL_DASHBOARD_CONFIG);

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, KPI_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const cpuMemChart = charts.find((c) => c?.chart.title === 'CPU 与内存使用率趋势');
  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');
  const sessionChart = charts.find((c) => c?.chart.title === '活动会话/连接趋势');

  const renderTrend = (chart: (typeof charts)[number], className: string) =>
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
        className={`${className} ${styles.compactTrend}`}
        styles={styles}
      />
    ) : null;

  // 共享 Firewall 盘按当前实例品牌在头部标识（如 Fortinet），品牌按 instance_id 识别
  // （品牌采集模板把 collect_type 如 snmp_fortinet 写进 instance_id 模板，可靠且不受自定义实例名影响）。
  const brandLabel = getBrandLabel(
    (dashboard.idValues?.length ? dashboard.idValues.join('_') : '') ||
      String(dashboard.instanceId ?? '')
  );

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

          {/* Row 2: 会话/连接趋势 span12 */}
          <div className={styles.sectionLabel}>会话与连接</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(sessionChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
