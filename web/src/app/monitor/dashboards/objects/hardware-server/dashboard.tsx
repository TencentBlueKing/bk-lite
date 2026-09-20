'use client';

import React from 'react';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  SummaryStatCard,
  useFilteredChartPanels,
  useFilteredSummaryCards,
  DashboardSectionLabel
} from '../common/dashboard-components';
import { CollectionStatusCard, TrendChartPanel } from '../../shared/widgets';
import { HARDWARE_SERVER_DASHBOARD_CONFIG } from './config';
import { HardwareDimensionTables, extractFirmwareLabel } from './dimension-tables';
import styles from './index.module.scss';

/** Status enums only — equal tiles in one row (no collection / power mix). */
const STATUS_TITLES = ['系统健康', '电源状态', 'BMC 健康', '处理器健康', '内存健康'];
/** Numeric KPI kept separate so it never stretches as a leftover grid cell. */
const POWER_TITLES = ['整机功耗'];
const CHART_TITLES = ['温度', '整机功耗', '风扇转速'];

export default function HardwareServerDashboardPage() {
  const dashboard = useSimpleDashboardData(HARDWARE_SERVER_DASHBOARD_CONFIG);
  const statusCards = useFilteredSummaryCards(dashboard.summaryCards, STATUS_TITLES);
  const powerCards = useFilteredSummaryCards(dashboard.summaryCards, POWER_TITLES);
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
          <section className={styles.healthOverview}>
            <CollectionStatusCard
              status={dashboard.collectionStatus}
              timeline={dashboard.collectionStatusTimeline}
              timelineHint={dashboard.collectionStatusTimelineHint}
              guideItems={[
                {
                  label: '采集状态',
                  detail: `展示当前选中时间窗内该 ${dashboard.objectFallbackName} 实例监控采集是否正常、缺失或异常。`
                },
                {
                  label: '状态时间线',
                  detail:
                    '时间线覆盖当前时间窗并均分为 18 段；绿色表示该段有采集，灰色表示该段无数据，红色表示采集或查询异常。'
                }
              ]}
              className={styles.collectionStrip}
              styles={styles}
            />

            <div className={styles.statusGrid}>
              {statusCards.map((summaryCard) => (
                <SummaryStatCard
                  key={summaryCard.card.title}
                  summaryCard={summaryCard}
                  className={styles.statusStatCard}
                  styles={styles}
                />
              ))}
            </div>

            {powerCards.length > 0 ? (
              <div className={styles.powerRow}>
                {powerCards.map((summaryCard) => (
                  <SummaryStatCard
                    key={summaryCard.card.title}
                    summaryCard={summaryCard}
                    className={styles.powerStatCard}
                    styles={styles}
                  />
                ))}
              </div>
            ) : null}
          </section>

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
