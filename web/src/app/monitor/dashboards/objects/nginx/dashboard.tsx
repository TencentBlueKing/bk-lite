'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards, DashboardSectionLabel } from '../common/dashboard-components';
import {
  RingChartPanel,
  TrendChartPanel
} from '../../shared/widgets';
import {
  dashboardModeOptions,
  resolveObjectDashboardMode,
  writeObjectDashboardMode,
  type ObjectDashboardMode
} from '../../shared/utils/pro-dashboard';
import { NGINX_DASHBOARD_CONFIG } from './config';
import NginxProLayout from './layered/nginx-pro-layout';
import styles from './index.module.scss';

const isNginxDashboardMode = (mode: string): mode is ObjectDashboardMode => (
  mode === 'dashboard' || mode === 'metrics' || mode === 'category'
);

const SUMMARY_TITLES = ['活跃连接数', '请求速率', '繁忙连接占比', '连接处理完成率'];
const CHART_TITLES = ['连接状态趋势', '连接接受/处理速率', '连接占比趋势'];
const RING_TITLES = ['连接状态分布'];
export default function NginxDashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const layout = resolveObjectDashboardMode('nginx', new URLSearchParams(searchParams.toString()));
  const dashboard = useSimpleDashboardData(NGINX_DASHBOARD_CONFIG);
  const onLayoutChange = (mode: string) => {
    if (!isNginxDashboardMode(mode) || mode === layout) return;
    const params = writeObjectDashboardMode(new URLSearchParams(searchParams.toString()), mode);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const [connectionTrendChart, rateTrendChart, connectionRatioChart] = charts;
  const [connectionRing] = rings;

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      preserveLayouts
      unifiedChrome
      viewSwitcher={{
        mode: layout,
        onChange: onLayoutChange,
        control: 'pill',
        options: dashboardModeOptions('nginx')
      }}
      categoryContent={(
        <NginxProLayout
          instanceId={String(dashboard.instanceId || '')}
          monitorObjectId={dashboard.monitorObjectId}
          timeValues={dashboard.timeValues}
          queryTimeRange={dashboard.queryTimeRange}
          instanceLoading={dashboard.instanceLoading}
          intervalSeconds={dashboard.currentInstanceInterval}
          reloadKey={dashboard.loadTick}
          linkedNodeId={dashboard.linkedNodeId}
          linkedIp={dashboard.linkedIp}
        />
      )}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />
          <DashboardSectionLabel styles={styles}>性能趋势与分布</DashboardSectionLabel>
          <FlexiblePanelSection styles={styles}>
            {/* R1: 速率折线 span8 + 连接分布环 span4 = 12 */}
            {rateTrendChart ? (
              <TrendChartPanel
                key={rateTrendChart.chart.title}
                title={rateTrendChart.chart.title}
                subtitle={rateTrendChart.chart.subtitle}
                guide={rateTrendChart.chart.guide}
                legends={rateTrendChart.legends}
                data={rateTrendChart.data}
                metric={rateTrendChart.metric}
                unit={rateTrendChart.unit}
                loading={dashboard.loading}
                seriesStyles={rateTrendChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span8} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {connectionRing ? (
              <RingChartPanel
                key={connectionRing.panel.title}
                title={connectionRing.panel.title}
                subtitle={connectionRing.panel.subtitle}
                guide={connectionRing.panel.guide}
                data={connectionRing.data}
                centerValue={connectionRing.centerValue}
                centerCaption={connectionRing.panel.centerCaption}
                isEmpty={connectionRing.isEmpty}
                className={styles.span4}
                styles={styles}
              />
            ) : null}
            {/* R2: 占比折线 + 连接状态趋势并排 */}
            {connectionRatioChart ? (
              <TrendChartPanel
                key={connectionRatioChart.chart.title}
                title={connectionRatioChart.chart.title}
                subtitle={connectionRatioChart.chart.subtitle}
                guide={connectionRatioChart.chart.guide}
                legends={connectionRatioChart.legends}
                data={connectionRatioChart.data}
                metric={connectionRatioChart.metric}
                unit={connectionRatioChart.unit}
                loading={dashboard.loading}
                seriesStyles={connectionRatioChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
            {connectionTrendChart ? (
              <TrendChartPanel
                key={connectionTrendChart.chart.title}
                title={connectionTrendChart.chart.title}
                subtitle={connectionTrendChart.chart.subtitle}
                guide={connectionTrendChart.chart.guide}
                legends={connectionTrendChart.legends}
                data={connectionTrendChart.data}
                metric={connectionTrendChart.metric}
                unit={connectionTrendChart.unit}
                loading={dashboard.loading}
                seriesStyles={connectionTrendChart.seriesStyles}
                onXRangeChange={dashboard.onXRangeChange}
                className={`${styles.span6} ${styles.compactTrend}`}
                styles={styles}
              />
            ) : null}
          </FlexiblePanelSection>
          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
