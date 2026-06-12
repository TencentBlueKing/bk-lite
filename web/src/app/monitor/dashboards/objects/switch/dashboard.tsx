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

  // 品牌自适应：只有当实例真正采集到健康指标（CPU/内存/温度有数据）时，才渲染健康面板。
  // 通用交换机（仅 IF-MIB）这些指标无数据 → 不渲染，避免出现空面板。
  const hasHealthData = (dashboard.summaryCards || []).some(
    (c) =>
      HEALTH_METRICS.includes(c.card?.metric) &&
      Array.isArray(c.trendData) &&
      c.trendData.length > 0
  );

  // 健康场景：运行时长 + CPU/内存/温度 + 入向 = 5 张 + 采集状态卡 = 6（kpiCols=6 正好一行）
  // 通用场景：运行时长 + 入向 + 出向 = 3 张 + 采集状态卡 = 4
  const kpiTitles = hasHealthData
    ? ['运行时长', ...HEALTH_KPI, '入向总流量']
    : UNIVERSAL_KPI;
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, kpiTitles);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);

  const cpuMemChart = charts.find((c) => c?.chart.title === 'CPU 与内存使用率趋势');
  const trafficChart = charts.find((c) => c?.chart.title === '设备收发流量趋势');
  const tempChart = charts.find((c) => c?.chart.title === '温度趋势');
  const fanChart = charts.find((c) => c?.chart.title === '风扇状态');
  const psuChart = charts.find((c) => c?.chart.title === '电源状态');

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

  // 共享 Switch 盘按当前实例品牌在头部标识（如 Cisco），便于辨认自适应切到的是哪个品牌的盘。
  // 品牌按 instance_id 识别（而非显示名）：品牌采集模板会把 collect_type（如 snmp_cisco）写进
  // instance_id 模板，因此 instance_id 是与品牌强绑定的可靠信号，不受用户自定义/ sysName 实例名影响。
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

          {hasHealthData ? (
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
