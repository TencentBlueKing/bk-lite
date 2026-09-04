'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  FlexiblePanelSection,
  KpiSection,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, TitleWithGuide, TrendChartPanel } from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency, topLabelBars } from '../../shared/utils';
import { DOCKER_DASHBOARD_CONFIG } from './config';
import { DOCKER_TOP_QUERIES } from './queries';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['运行容器数', '停止容器占比', '时段内重启', '容器 CPU 使用率', '容器内存使用率'];
const RESOURCE_CHART_TITLES = ['容器资源使用趋势', '块设备吞吐趋势'];
const NETWORK_CHART_TITLES = ['网络吞吐趋势', '网络错误速率'];
const TOP_CONCURRENCY = 2;

export default function DockerDashboardPage() {
  const dashboard = useSimpleDashboardData(DOCKER_DASHBOARD_CONFIG);
  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const resourceCharts = useFilteredChartPanels(dashboard.chartPanels, RESOURCE_CHART_TITLES);
  const networkCharts = useFilteredChartPanels(dashboard.chartPanels, NETWORK_CHART_TITLES);

  const [resourceChart, blockIoChart] = resourceCharts;
  const [networkChart, networkErrorChart] = networkCharts;

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
    runWithConcurrency(DOCKER_TOP_QUERIES, TOP_CONCURRENCY, async (q) =>
      getInstanceQuery(
        buildSearchParams(
          q.query,
          q.unit,
          idValues,
          instanceIdKeys,
          timeValues,
          undefined,
          false,
          currentInstanceInterval
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentInstanceInterval, idValuesKey, timeKey, isDashboardMode, instanceIdKeys, getInstanceQuery, loadTick]);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <div className={styles.sectionLabel}>性能趋势</div>
          <FlexiblePanelSection styles={styles}>
            {[resourceChart, blockIoChart].map((chart) => chart ? (
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

          <div className={styles.sectionLabel}>网络观察</div>
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

          <div className={styles.sectionLabel}>容器资源排行</div>
          <section className={styles.dashboardSection}>
            <div className={styles.sectionGrid}>
              {DOCKER_TOP_QUERIES.map((q) => (
                <HorizontalBarPanel
                  key={q.key}
                  styles={styles}
                  className={`${styles.panel} ${styles.span6}`}
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
            </div>
          </section>
        </>
      }
    />
  );
}
