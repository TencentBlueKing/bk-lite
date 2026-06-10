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
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, TitleWithGuide } from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency } from '../../shared/utils';
import { POSTGRESQL_DASHBOARD_CONFIG } from './config';
import { PG_TOP_DB_QUERIES } from './queries';
import { topDbBars } from './parse';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['活跃连接数', '事务提交速率', '缓存命中率'];
const PRIMARY_CHART_TITLES = ['事务提交与回滚', '缓存与磁盘读', '检查点趋势'];
const SECONDARY_CHART_TITLES = ['数据操作速率', '查询行读取趋势', '缓冲区写入活动'];
const BAR_TITLES = ['异常事件热点', '缓冲区写入来源'];
const TOP_DB_CONCURRENCY = 3;

export default function PostgresqlDashboardPage() {
  const dashboard = useSimpleDashboardData(POSTGRESQL_DASHBOARD_CONFIG);
  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  // 「数据库压力排行」为 bespoke 取数:config-driven 核心无法表达按 dbname 的动态 TopN,
  // 故复用实例/时间上下文,自行发 topk(by dbname) 查询并解析为 BarList。
  const { idValues, timeValues, isDashboardMode } = dashboard;
  const [topDb, setTopDb] = useState<Record<string, BarItem[]>>({});
  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  useEffect(() => {
    if (!isDashboardMode) {
      setTopDb({});
      return;
    }
    let active = true;
    runWithConcurrency(PG_TOP_DB_QUERIES, TOP_DB_CONCURRENCY, async (q) =>
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idValuesKey, timeKey, isDashboardMode, instanceIdKeys, getInstanceQuery]);

  return (
    <DashboardShell
      dashboard={dashboard}
      styles={styles}
      dashboardContent={
        <>
          <div className={styles.sectionLabel}>健康概览</div>
          <KpiSection dashboard={dashboard} summaryCards={summaryCards} styles={styles} />

          <div className={styles.sectionLabel}>事务与缓存</div>
          <TrendSection charts={primaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <div className={styles.sectionLabel}>行操作与查询</div>
          <TrendSection charts={secondaryCharts} onXRangeChange={dashboard.onXRangeChange} loading={dashboard.loading} styles={styles} />

          <div className={styles.sectionLabel}>异常与写入来源</div>
          <InsightSection bars={bars} barSpanClass={() => styles.span6} styles={styles} />

          <div className={styles.sectionLabel}>数据库压力排行</div>
          <section className={styles.dashboardSection}>
            <div className={styles.sectionGrid}>
              {PG_TOP_DB_QUERIES.map((q) => (
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
