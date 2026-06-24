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
import { SWITCH_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

// 通用交换机始终展示的面板（所有品牌都采集 IF-MIB 接口 / 运行时长 / 流量）
const UNIVERSAL_KPI = ['运行时长', '入向总流量', '出向总流量'];
const HEALTH_KPI = ['CPU 使用率', '内存使用率', '最高温度'];
// 仅当实例采集到厂商私有健康指标（如思科 CPU/内存/温度）时才显示的健康面板
const HEALTH_METRICS = [
  'device_cpu_usage',
  'device_memory_usage',
  'device_temperature_celsius',
  'device_fan_state'
];

const CHART_TITLES = [
  'CPU 与内存使用率趋势',
  '设备收发流量趋势',
  '温度趋势',
  '风扇状态',
  '电源状态'
];

export default function SwitchDashboardPage() {
  const dashboard = useSimpleDashboardData(SWITCH_DASHBOARD_CONFIG);

  // 品牌按 instance_id 识别（collect_type 如 snmp_cisco 写在 instance_id 模板里）。
  const idText =
    (dashboard.idValues?.length ? dashboard.idValues.join('_') : '') ||
    String(dashboard.instanceId ?? '');
  const resolved = resolveCapability('switch', idText);

  // 健康区段开关：品牌命中时按能力矩阵判定（确定性，区分"不支持"与"暂时没数据"）；
  // 未命中品牌时退回原有"数据存在性"判定，保证不退化已可用实例。
  const hasHealthData = (dashboard.summaryCards || []).some(
    (c) =>
      HEALTH_METRICS.includes(c.card?.metric) &&
      Array.isArray(c.trendData) &&
      c.trendData.length > 0
  );
  const hasHealthCapability = resolved.matched
    ? (['cpu', 'memory', 'temperature'] as const).some((cap) => resolved.capabilities.has(cap))
    : hasHealthData;

  // 健康场景：运行时长 + CPU/内存/温度 + 入向 = 5 张 + 采集状态卡 = 6（kpiCols=6 正好一行）
  // 通用场景：运行时长 + 入向 + 出向 = 3 张 + 采集状态卡 = 4
  const kpiTitles = hasHealthCapability
    ? ['运行时长', ...HEALTH_KPI, '入向总流量']
    : UNIVERSAL_KPI;
  const filteredCards = useFilteredSummaryCards(dashboard.summaryCards, kpiTitles);
  // 品牌命中时按"矩阵×数据"门控卡片（不支持→剔除；支持但无数据→保留显示 --）；未命中不动。
  const summaryCards = resolved.matched
    ? filteredCards.filter((c) =>
      isMetricVisible(
        resolved,
        'switch',
        c.card?.metric,
        Array.isArray(c.trendData) && c.trendData.length > 0
      )
    )
    : filteredCards;
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const cpuMemChart = charts.find((c) => c?.chart.title === 'CPU 与内存使用率趋势');
  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');
  const tempChart = charts.find((c) => c?.chart.title === '温度趋势');
  const fanChart = charts.find((c) => c?.chart.title === '风扇状态');
  const psuChart = charts.find((c) => c?.chart.title === '电源状态');

  const renderTrend = (chart: (typeof charts)[number], className: string) =>
    chart && isMetricVisible(resolved, 'switch', chart.chart.metric, true) ? (
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

          {hasHealthCapability ? (
            <>
              {/* Row 1: CPU&内存 span6 + 收发流量 span6 */}
              <div className={styles.sectionLabel}>性能趋势</div>
              <FlexiblePanelSection styles={styles}>
                {renderTrend(cpuMemChart, styles.span6)}
                {renderTrend(trafficChart, styles.span6)}
              </FlexiblePanelSection>

              {/* Row 2: 温度 + 风扇状态 + 电源状态 三张折线 span4 */}
              <div className={styles.sectionLabel}>温度与硬件状态</div>
              <FlexiblePanelSection styles={styles}>
                {renderTrend(tempChart, styles.span4)}
                {renderTrend(fanChart, styles.span4)}
                {renderTrend(psuChart, styles.span4)}
              </FlexiblePanelSection>
            </>
          ) : (
            <>
              {/* 通用交换机：只展示收发流量趋势（接口/流量是所有交换机都有的标准指标） */}
              <div className={styles.sectionLabel}>流量趋势</div>
              <FlexiblePanelSection styles={styles}>
                {renderTrend(trafficChart, styles.span12)}
              </FlexiblePanelSection>
            </>
          )}
        </>
      }
    />
  );
}
