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
import { ORACLE_DASHBOARD_CONFIG } from './config';
import { ORACLE_TOP_QUERIES } from './queries';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['数据库状态', '会话数', 'User I/O 等待'];
const CHART_TITLES = ['SQL 活性', '事务提交与回滚', 'Wait Class 概览', '内存使用'];
const TOP_CONCURRENCY = 2;

export default function OracleDashboardPage() {
  const dashboard = useSimpleDashboardData(ORACLE_DASHBOARD_CONFIG);
  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, CHART_TITLES);
  const [activityChart, txnChart, waitChart, memoryChart] = charts;

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
    runWithConcurrency(ORACLE_TOP_QUERIES, TOP_CONCURRENCY, async (q) =>
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
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>活性与事务</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(activityChart, styles.span6)}
            {renderChart(txnChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>等待类与内存</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(waitChart, styles.span6)}
            {renderChart(memoryChart, styles.span6)}
          </FlexiblePanelSection>

          <div className={styles.sectionLabel}>表空间与资源排行</div>
          <section className={styles.dashboardSection}>
            <div className={styles.sectionGrid}>
              {ORACLE_TOP_QUERIES.map((q) => (
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
