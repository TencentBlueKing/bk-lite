'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  InsightSection,
  KpiSection,
  TrendSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredRingPanels,
  useFilteredSummaryCards, DashboardSectionLabel } from '../common/dashboard-components';
import { HorizontalBarPanel, TitleWithGuide } from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency } from '../../shared/utils';
import {
  dashboardModeOptions,
  resolveObjectDashboardMode,
  writeObjectDashboardMode,
  type ObjectDashboardMode
} from '../../shared/utils/pro-dashboard';
import { MSSQL_DASHBOARD_CONFIG } from './config';
import { MSSQL_TOP_DB_QUERIES } from './queries';
import { topDbBars } from './parse';
import MssqlCategoryLayout from './layered/category-layout';
import { MssqlIdentityExtra } from './layered/identity';
import { MSSQL_PRO_METRIC_NAMES, MSSQL_PRO_METRICS, MSSQL_PRO_NAMES } from './layered/queries';
import { mssqlLatest } from './layered/series';
import styles from './index.module.scss';

// 数据库类对象首行统一带「运行时长」(放首位);采集状态 + 5 张 KPI = 6 列一行。
// 用运行时长替换信息密度较低的「信号等待占比」(其语义仍由「等待时间趋势」图保留)。
const SUMMARY_TITLES = ['运行时长', '读延迟', '批量请求速率', '缓存命中率', '卷可用空间'];
const PRIMARY_CHART_TITLES = ['等待时间趋势', '请求耗时趋势', '读写延迟'];
// 一线排障：阻塞/内存授予与编译/死锁紧挨主趋势，单独成节避免挤进 CPU/吞吐。
const CONCURRENCY_CHART_TITLES = ['并发与内存压力', '计划缓存与死锁'];
const SECONDARY_CHART_TITLES = ['CPU 使用情况', '读写吞吐'];
const RING_TITLES = ['存储空间分布'];
const BAR_TITLES = ['调度器压力'];
const TOP_DB_CONCURRENCY = 3;

const isMssqlDashboardMode = (mode: string): mode is ObjectDashboardMode => (
  mode === 'dashboard' || mode === 'metrics' || mode === 'category'
);

export default function MssqlDashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const layout = resolveObjectDashboardMode('mssql', new URLSearchParams(searchParams.toString()));
  const proConfig = useMemo(() => ({
    ...MSSQL_DASHBOARD_CONFIG,
    metrics: MSSQL_PRO_METRICS
  }), []);
  const dashboard = useSimpleDashboardData(
    layout === 'category' ? proConfig : MSSQL_DASHBOARD_CONFIG,
    layout === 'category'
      ? { metricNames: MSSQL_PRO_METRIC_NAMES, reuseLoadedSeries: true }
      : undefined
  );
  const { getInstanceQuery } = useViewApi();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const concurrencyCharts = useFilteredChartPanels(dashboard.chartPanels, CONCURRENCY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  // 「数据库压力排行」为 bespoke 取数:config-driven 核心无法表达按 database 的动态 TopN,
  // 故复用实例/时间上下文,自行发 topk(by database) 查询并解析为 BarList。
  const { idValues, timeValues, isDashboardMode, loadTick, currentInstanceInterval } = dashboard;
  const [topDb, setTopDb] = useState<Record<string, BarItem[]>>({});
  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  useEffect(() => {
    if (layout !== 'dashboard' || !isDashboardMode || !idValues.length) {
      setTopDb({});
      return;
    }
    let active = true;
    runWithConcurrency(MSSQL_TOP_DB_QUERIES, TOP_DB_CONCURRENCY, async (q) =>
      // autoConvert=false:禁用服务端单位自动换算,否则会与前端 formatMetricValue 双重换算
      //(如 ms 被后端先换成 hour,前端再按 ms 格式化,量级错乱)。见 postgresql 同因。
      getInstanceQuery(buildSearchParams(q.query, q.unit, idValues, instanceIdKeys, timeValues, undefined, false, currentInstanceInterval, {
        monitorObjectId: dashboard.monitorObjectId,
        instanceId: dashboard.instanceId,
      }))
        .then((res: any) => [q.key, topDbBars(res, q.unit, q.color)] as const)
        .catch(() => [q.key, [] as BarItem[]] as const)
    ).then((entries) => {
      if (active) {
        setTopDb(Object.fromEntries(entries));
      }
    });
    return () => {
      active = false;
    };
    // loadTick 随核心盘每次加载(含自动刷新)递增,使 TopN 与核心盘同步刷新。
  }, [currentInstanceInterval, idValuesKey, timeKey, isDashboardMode, instanceIdKeys, getInstanceQuery, layout, loadTick]);

  const onLayoutChange = (mode: string) => {
    if (!isMssqlDashboardMode(mode) || mode === layout) return;
    const params = writeObjectDashboardMode(new URLSearchParams(searchParams.toString()), mode);
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      preserveLayouts
      unifiedChrome
      identityExtra={layout === 'category' ? (
        <MssqlIdentityExtra
          instanceName={dashboard.resolvedInstanceName}
          instanceId={String(dashboard.instanceId || '')}
          idValues={dashboard.idValues}
          uptimeMinutes={mssqlLatest(dashboard.metricSeries, MSSQL_PRO_NAMES.uptime)}
          version={dashboard.instanceVersion}
          port={dashboard.instancePort}
        />
      ) : undefined}
      viewSwitcher={{
        mode: layout,
        onChange: onLayoutChange,
        control: 'pill',
        options: dashboardModeOptions('mssql')
      }}
      pageClassName={layout === 'category' ? styles.proPage : undefined}
      shellClassName={layout === 'category' ? styles.proShell : undefined}
      categoryContent={(
        <MssqlCategoryLayout
          instanceId={dashboard.instanceId}
          monitorObjectId={dashboard.monitorObjectId}
          idValues={dashboard.idValues}
          instanceIdKeys={instanceIdKeys}
          timeValues={dashboard.timeValues}
          queryTimeRange={dashboard.queryTimeRange}
          loading={dashboard.loading}
          pendingMetricNames={dashboard.pendingMetricNames}
          metricMap={dashboard.metricSeries}
          reloadKey={dashboard.loadTick}
          minStepSeconds={dashboard.currentInstanceInterval}
        />
      )}
      dashboardContent={
        <>
          <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={6} styles={styles} />

          <DashboardSectionLabel styles={styles}>性能与等待趋势</DashboardSectionLabel>
          <TrendSection charts={primaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <DashboardSectionLabel styles={styles}>并发与故障</DashboardSectionLabel>
          <TrendSection
            charts={concurrencyCharts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => styles.span6}
            styles={styles}
          />

          <DashboardSectionLabel styles={styles}>存储与调度</DashboardSectionLabel>
          <InsightSection
            rings={rings}
            bars={bars}
            ringSpanClass={() => styles.span6}
            barSpanClass={() => styles.span6}
            styles={styles}
          />

          <DashboardSectionLabel styles={styles}>CPU 与 I/O 吞吐</DashboardSectionLabel>
          <TrendSection
            charts={secondaryCharts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => styles.span6}
            styles={styles}
          />

          <DashboardSectionLabel styles={styles}>数据库压力排行</DashboardSectionLabel>
          <section className={styles.dashboardSection}>
            <div className={styles.sectionGrid}>
              {MSSQL_TOP_DB_QUERIES.map((q) => (
                <HorizontalBarPanel
                  key={q.key}
                  styles={styles}
                  className={`${styles.panel} ${styles.span4}`}
                  title={<TitleWithGuide styles={styles} title={q.title} items={q.guide} className={styles.panelTitleWithGuide} />}
                  items={topDb[q.key] || []}
                />
              ))}
            </div>
          </section>

          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
