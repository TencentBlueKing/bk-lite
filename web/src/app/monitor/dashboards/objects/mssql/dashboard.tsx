'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
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
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, TitleWithGuide } from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency } from '../../shared/utils';
import { MSSQL_DASHBOARD_CONFIG } from './config';
import { MSSQL_TOP_DB_QUERIES } from './queries';
import { topDbBars } from './parse';
import styles from './index.module.scss';

// 数据库类对象首行统一带「运行时长」(放首位);KpiSection 上限 6 列(含采集状态卡)即最多 5 张 KPI,
// 故用运行时长替换信息密度较低的「信号等待占比」(其语义仍由「等待时间趋势」图保留)。
const SUMMARY_TITLES = ['运行时长', '读延迟', '批量请求速率', '缓存命中率', '卷可用空间'];
const PRIMARY_CHART_TITLES = ['等待时间趋势', '请求耗时趋势', '读写延迟'];
const SECONDARY_CHART_TITLES = ['CPU 使用情况', '读写吞吐'];
const RING_TITLES = ['缓存命中分布', '存储空间分布'];
const BAR_TITLES = ['调度器压力', '请求资源消耗'];
const TOP_DB_CONCURRENCY = 3;

export default function MssqlDashboardPage() {
  const dashboard = useSimpleDashboardData(MSSQL_DASHBOARD_CONFIG);
  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  // 「数据库压力排行」为 bespoke 取数:config-driven 核心无法表达按 database 的动态 TopN,
  // 故复用实例/时间上下文,自行发 topk(by database) 查询并解析为 BarList。
  const { idValues, timeValues, isDashboardMode, loadTick } = dashboard;
  const [topDb, setTopDb] = useState<Record<string, BarItem[]>>({});
  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  useEffect(() => {
    if (!isDashboardMode) {
      setTopDb({});
      return;
    }
    let active = true;
    runWithConcurrency(MSSQL_TOP_DB_QUERIES, TOP_DB_CONCURRENCY, async (q) =>
      getInstanceQuery(buildSearchParams(q.query, q.unit, idValues, instanceIdKeys, timeValues))
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idValuesKey, timeKey, isDashboardMode, instanceIdKeys, getInstanceQuery, loadTick]);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>性能与等待趋势</div>
          <TrendSection charts={primaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <div className={styles.sectionLabel}>缓存与存储分布</div>
          <InsightSection rings={rings} bars={[]} ringSpanClass={() => styles.span6} styles={styles} />

          <div className={styles.sectionLabel}>调度与请求压力</div>
          <InsightSection bars={bars} barSpanClass={() => styles.span6} styles={styles} />

          <div className={styles.sectionLabel}>CPU 与 I/O 吞吐</div>
          <TrendSection
            charts={secondaryCharts}
            onXRangeChange={dashboard.onXRangeChange}
            loading={dashboard.loading}
            spanClass={() => styles.span6}
            styles={styles}
          />

          <div className={styles.sectionLabel}>数据库压力排行</div>
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
