'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Tabs } from 'antd';
import useViewApi from '@/app/monitor/api/view';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards,
  DashboardSectionLabel
} from '../common/dashboard-components';
import {
  HorizontalBarPanel,
  RingChartPanel,
  TitleWithGuide,
  TrendChartPanel
} from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency, topLabelBars } from '../../shared/utils';
import { HOST_DASHBOARD_CONFIG } from './config';
import { HOST_TOP_QUERIES } from './queries';
import { HostDeepAnalysis } from './host-deep-analysis';
import styles from './index.module.scss';

const TOP_CHART_TITLES = ['资源使用趋势', '系统负载趋势'];
const NETWORK_CHART_TITLES = ['网络吞吐趋势', '网络错误速率'];
const DISK_PROCESS_CHART_TITLES = ['磁盘吞吐趋势', '进程异常趋势'];
const RING_TITLES = ['CPU 时间分布'];
const TOP_CONCURRENCY = 1;

export default function HostDashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const dashboard = useSimpleDashboardData(HOST_DASHBOARD_CONFIG);
  const { getInstanceQuery } = useViewApi();

  const [activeTab, setActiveTab] = useState<'overview' | 'deep'>(() => {
    return searchParams.get('tab') === 'deep' ? 'deep' : 'overview';
  });

  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam === 'deep') {
      setActiveTab('deep');
    } else if (tabParam === 'overview') {
      setActiveTab('overview');
    }
  }, [searchParams]);

  const handleTabChange = (key: string) => {
    const nextTab = key === 'deep' ? 'deep' : 'overview';
    setActiveTab(nextTab);
    const params = new URLSearchParams(searchParams.toString());
    if (nextTab === 'deep') {
      params.set('tab', 'deep');
    } else {
      params.delete('tab');
    }
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const summaryCards = useFilteredSummaryCards(
    dashboard.summaryCards,
    ['运行时长', 'CPU 使用率', '内存使用率', '磁盘使用率', '1 分钟负载']
  );
  const topCharts = useFilteredChartPanels(dashboard.chartPanels, TOP_CHART_TITLES);
  const networkCharts = useFilteredChartPanels(dashboard.chartPanels, NETWORK_CHART_TITLES);
  const diskProcessCharts = useFilteredChartPanels(dashboard.chartPanels, DISK_PROCESS_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [resourceChart, loadChart] = topCharts;
  const [networkChart, networkErrorChart] = networkCharts;
  const [diskChart, processAnomalyChart] = diskProcessCharts;
  const [cpuRing] = rings;

  const { idValues, timeValues, isDashboardMode, loadTick, currentInstanceInterval } = dashboard;
  const [topBars, setTopBars] = useState<Record<string, BarItem[]>>({});
  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  useEffect(() => {
    if (!isDashboardMode || !idValues.length) {
      setTopBars({});
      return;
    }
    let active = true;
    runWithConcurrency(HOST_TOP_QUERIES, TOP_CONCURRENCY, async (q) =>
      getInstanceQuery(
        buildSearchParams(
          q.query,
          q.unit,
          idValues,
          instanceIdKeys,
          timeValues,
          undefined,
          false,
          currentInstanceInterval,
          { monitorObjectId: dashboard.monitorObjectId, instanceId: dashboard.instanceId }
        )
      )
        .then((res: any) => [q.key, topLabelBars(res, q.unit, q.color, q.labelKeys)] as const)
        .catch(() => [q.key, [] as BarItem[]] as const)
    ).then((entries) => {
      if (active) setTopBars(Object.fromEntries(entries));
    });
    return () => {
      active = false;
    };
  }, [currentInstanceInterval, idValuesKey, timeKey, isDashboardMode, instanceIdKeys, getInstanceQuery, loadTick]);

  const tabsSlot = (
    <div className={styles.pageTabsBar}>
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          { key: 'overview', label: '概览' },
          { key: 'deep', label: '深度分析' }
        ]}
      />
    </div>
  );

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      title={activeTab === 'deep' ? '主机深度分析' : dashboard.pageTitle}
      tabsSlot={tabsSlot}
      dashboardContent={
        activeTab === 'deep' ? (
          <HostDeepAnalysis
            dashboard={dashboard}
            styles={styles}
            onViewAllProcesses={() => dashboard.setDisplayMode('metrics')}
          />
        ) : (
          <>
            <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
            <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

            <DashboardSectionLabel styles={styles}>性能与分布</DashboardSectionLabel>
            <FlexiblePanelSection styles={styles}>
              {[resourceChart, loadChart].map((chart) => chart ? (
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
                  className={`${styles.span4} ${styles.compactTrend}`}
                  styles={styles}
                />
              ) : null)}
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
              {[networkChart, networkErrorChart].map((chart) => chart ? (
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
                  className={`${styles.span6} ${styles.compactTrend}`}
                  styles={styles}
                />
              ) : null)}
            </FlexiblePanelSection>

            <DashboardSectionLabel styles={styles}>磁盘与进程</DashboardSectionLabel>
            <FlexiblePanelSection styles={styles}>
              {diskChart ? (
                <TrendChartPanel
                  key={diskChart.chart.title}
                  title={diskChart.chart.title}
                  subtitle={diskChart.chart.subtitle}
                  guide={diskChart.chart.guide}
                  legends={diskChart.legends}
                  data={diskChart.data}
                  metric={diskChart.metric}
                  unit={diskChart.unit}
                  loading={dashboard.loading}
                  seriesStyles={diskChart.seriesStyles}
                  onXRangeChange={dashboard.onXRangeChange}
                  className={`${styles.span4} ${styles.compactTrend}`}
                  styles={styles}
                />
              ) : null}
              {HOST_TOP_QUERIES.map((q) => (
                <HorizontalBarPanel
                  key={q.key}
                  styles={styles}
                  className={`${styles.panel} ${styles.span4}`}
                  title={
                    <TitleWithGuide
                      styles={styles}
                      title={q.title}
                      items={q.guide}
                      className={styles.panelTitleWithGuide}
                    />
                  }
                  items={topBars[q.key] || []}
                />
              ))}
              {processAnomalyChart ? (
                <TrendChartPanel
                  key={processAnomalyChart.chart.title}
                  title={processAnomalyChart.chart.title}
                  subtitle={processAnomalyChart.chart.subtitle}
                  guide={processAnomalyChart.chart.guide}
                  legends={processAnomalyChart.legends}
                  data={processAnomalyChart.data}
                  metric={processAnomalyChart.metric}
                  unit={processAnomalyChart.unit}
                  loading={dashboard.loading}
                  seriesStyles={processAnomalyChart.seriesStyles}
                  onXRangeChange={dashboard.onXRangeChange}
                  className={`${styles.span4} ${styles.compactTrend}`}
                  styles={styles}
                />
              ) : null}
            </FlexiblePanelSection>
          </>
        )
      }
    />
  );
}
