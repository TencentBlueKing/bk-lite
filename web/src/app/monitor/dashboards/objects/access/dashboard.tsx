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
import { ACCESS_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

// 接入设备(BDCOM OLT/交换机)仅采 IF-MIB 64 位 HC 接口流量 + 运行时长，故健康面板仅含运行时长与收发总流量。
// 光功率/PON 口/温度等健康指标因 MIB per-row 索引带行级过滤而 N/A；取不到的实例对应卡片显示「--」、趋势显示空。
const KPI_TITLES = ['运行时长', '入向总流量', '出向总流量'];
const CHART_TITLES = ['设备收发流量趋势'];

export default function AccessDashboardPage() {
  const dashboard = useSimpleDashboardData(ACCESS_DASHBOARD_CONFIG);

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, KPI_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');

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

  // 共享 Access 盘按当前实例品牌在头部标识（如 BDCOM）。品牌按 instance_id 识别
  // （品牌采集模板把 collect_type 如 snmp_bdcom 写进 instance_id 模板，可靠且不受自定义实例名影响）。
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

          {/* Row 1: 设备收发流量趋势 span12 */}
          <div className={styles.sectionLabel}>性能趋势</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(trafficChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
