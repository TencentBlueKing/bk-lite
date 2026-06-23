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
import { TRANSMISSION_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

// 传输设备保守基线：仅运行时长 + 接口收发流量可干净采（IF-MIB 64位 HC）。
// 温度/光功率/激光偏置电流为 per-row 索引表带行级过滤 → N/A，故不渲染健康折线，避免伪造。
const KPI_TITLES = ['运行时长', '入向总流量', '出向总流量'];
const CHART_TITLES = ['设备收发流量趋势'];

export default function TransmissionDashboardPage() {
  const dashboard = useSimpleDashboardData(TRANSMISSION_DASHBOARD_CONFIG);

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

  // 共享 Transmission 盘按当前实例品牌在头部标识（如 Ciena）。品牌按 instance_id 识别
  // （品牌采集模板把 collect_type 如 snmp_ciena 写进 instance_id 模板，可靠且不受自定义实例名影响）。
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

          {/* 性能趋势：设备收发流量 span12 */}
          <div className={styles.sectionLabel}>性能趋势</div>
          <FlexiblePanelSection styles={styles}>
            {renderTrend(trafficChart, styles.span12)}
          </FlexiblePanelSection>
        </>
      }
    />
  );
}
