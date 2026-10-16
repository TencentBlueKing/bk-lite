'use client';

import React, { useEffect, useState } from 'react';
import useViewApi from '@/app/monitor/api/view';
import {
  DashboardSectionLabel,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels
} from '../common/dashboard-components';
import type { PreparedChartPanel } from '../common/simple-dashboard-core';
import {
  HorizontalBarPanel,
  RingChartPanel,
  TitleWithGuide,
  TrendChartPanel
} from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency, topLabelBars } from '../../shared/utils';
import { HOST_TOP_QUERIES } from './queries';
import type { HostDetailLayoutProps } from './detail-layout';

const TOP_CHART_TITLES = ['资源使用趋势', '系统负载趋势'];
const NETWORK_CHART_TITLES = ['网络吞吐趋势', '网络错误速率'];
const DISK_PROCESS_CHART_TITLES = ['磁盘吞吐趋势', '进程异常趋势'];
const RING_TITLES = ['CPU 时间分布'];
const TOP_CONCURRENCY = 1;

/** 经典布局：健康概览、性能与分布、网络观察、磁盘与进程。 */
export default function HostLegacyLayout({
  styles,
  dashboard,
  instanceIdKeys
}: HostDetailLayoutProps) {
  const { getInstanceQuery } = useViewApi();
  const [topBars, setTopBars] = useState<Record<string, BarItem[]>>({});
  const topCharts = useFilteredChartPanels(dashboard.chartPanels, TOP_CHART_TITLES);
  const networkCharts = useFilteredChartPanels(dashboard.chartPanels, NETWORK_CHART_TITLES);
  const diskProcessCharts = useFilteredChartPanels(dashboard.chartPanels, DISK_PROCESS_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const [resourceChart, loadChart] = topCharts;
  const [networkChart, networkErrorChart] = networkCharts;
  const [diskChart, processAnomalyChart] = diskProcessCharts;
  const [cpuRing] = rings;

  const { idValues, timeValues, isDashboardMode, loadTick, currentInstanceInterval } = dashboard;
  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  useEffect(() => {
    if (!isDashboardMode || !idValues.length) {
      setTopBars({});
      return;
    }
    let active = true;
    runWithConcurrency(HOST_TOP_QUERIES, TOP_CONCURRENCY, async (query) =>
      getInstanceQuery(
        buildSearchParams(
          query.query,
          query.unit,
          idValues,
          instanceIdKeys,
          timeValues,
          undefined,
          false,
          currentInstanceInterval,
          { monitorObjectId: dashboard.monitorObjectId, instanceId: dashboard.instanceId }
        )
      )
        .then((result) => [query.key, topLabelBars(result, query.unit, query.color, query.labelKeys)] as const)
        .catch(() => [query.key, [] as BarItem[]] as const)
    ).then((entries) => {
      if (active) setTopBars(Object.fromEntries(entries));
    });
    return () => {
      active = false;
    };
  }, [
    currentInstanceInterval,
    dashboard.instanceId,
    dashboard.monitorObjectId,
    getInstanceQuery,
    idValues,
    idValuesKey,
    instanceIdKeys,
    isDashboardMode,
    loadTick,
    timeKey,
    timeValues
  ]);

  const renderTrend = (chart: PreparedChartPanel | undefined, className: string) => chart ? (
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
      className={className}
      styles={styles}
    />
  ) : null;

  return (
    <>
      <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
      <KpiSection dashboard={dashboard} summaryCards={dashboard.summaryCards} kpiCols={6} styles={styles} />

      <DashboardSectionLabel styles={styles}>性能与分布</DashboardSectionLabel>
      <FlexiblePanelSection styles={styles}>
        {renderTrend(resourceChart, `${styles.span4} ${styles.compactTrend}`)}
        {renderTrend(loadChart, `${styles.span4} ${styles.compactTrend}`)}
        {cpuRing ? (
          <RingChartPanel
            key={cpuRing.panel.title}
            title={cpuRing.panel.title}
            subtitle={cpuRing.panel.subtitle}
            guide={cpuRing.panel.guide}
            data={cpuRing.data}
            centerValue={cpuRing.centerValue}
            centerCaption={cpuRing.panel.centerCaption}
            isEmpty={cpuRing.isEmpty}
            className={styles.span4}
            styles={styles}
          />
        ) : null}
      </FlexiblePanelSection>

      <DashboardSectionLabel styles={styles}>网络观察</DashboardSectionLabel>
      <FlexiblePanelSection styles={styles}>
        {renderTrend(networkChart, `${styles.span6} ${styles.compactTrend}`)}
        {renderTrend(networkErrorChart, `${styles.span6} ${styles.compactTrend}`)}
      </FlexiblePanelSection>

      <DashboardSectionLabel styles={styles}>磁盘与进程</DashboardSectionLabel>
      <FlexiblePanelSection styles={styles}>
        {renderTrend(diskChart, `${styles.span4} ${styles.compactTrend}`)}
        {HOST_TOP_QUERIES.map((query) => (
          <HorizontalBarPanel
            key={query.key}
            styles={styles}
            className={`${styles.panel} ${styles.span4}`}
            title={
              <TitleWithGuide
                styles={styles}
                title={query.title}
                items={query.guide}
                className={styles.panelTitleWithGuide}
              />
            }
            items={topBars[query.key] || []}
          />
        ))}
        {renderTrend(processAnomalyChart, `${styles.span4} ${styles.compactTrend}`)}
      </FlexiblePanelSection>
    </>
  );
}
