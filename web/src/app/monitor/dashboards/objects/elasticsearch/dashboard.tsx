'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import useViewApi from '@/app/monitor/api/view';
import { useSimpleDashboardData } from '../common/simple-dashboard-core';
import {
  DashboardShell,
  DetailSection,
  FlexiblePanelSection,
  KpiSection,
  useFilteredBarPanels,
  useFilteredChartPanels,
  useFilteredSummaryCards
} from '../common/dashboard-components';
import { HorizontalBarPanel, TitleWithGuide, TrendChartPanel } from '../../shared/widgets';
import type { BarItem } from '../../shared/widgets';
import { buildSearchParams, runWithConcurrency } from '../../shared/utils';
import { ClusterHealthCard } from './cluster-health-card';
import { ELASTICSEARCH_DASHBOARD_CONFIG } from './config';
import { ES_TOP_NODE_QUERIES } from './queries';
import { topNodeBars } from './parse';
import styles from './index.module.scss';

const HEALTH_CARD_TITLE = '集群健康状态';
const SUMMARY_TITLES = ['未分配分片', '主分片分配率', '节点可用磁盘', 'JVM 堆使用率'];
const PRIMARY_CHART_TITLES = ['线程池队列', '熔断器触发', 'HTTP 新建连接'];
const SECONDARY_CHART_TITLES = ['资源使用率', 'GC 耗时趋势'];
const BAR_TITLES = ['线程池压力', '熔断器热点'];
const TOP_NODE_CONCURRENCY = 3;

export default function ElasticsearchDashboardPage() {
  const dashboard = useSimpleDashboardData(ELASTICSEARCH_DASHBOARD_CONFIG);
  const { getInstanceQuery } = useViewApi();
  const searchParams = useSearchParams();
  const instanceIdKeys = useMemo(
    () => (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean),
    [searchParams]
  );

  const healthCard = useMemo(
    () => dashboard.summaryCards.find((c) => c.card.title === HEALTH_CARD_TITLE),
    [dashboard.summaryCards]
  );
  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const primaryCharts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const secondaryCharts = useFilteredChartPanels(dashboard.chartPanels, SECONDARY_CHART_TITLES);
  const bars = useFilteredBarPanels(dashboard.barPanels, BAR_TITLES);

  const [threadQueueChart, breakerTrigChart, httpChart] = primaryCharts;
  const [resourceChart, gcChart] = secondaryCharts;
  const [threadPoolBar, breakerBar] = bars;

  const renderChart = (chart: typeof primaryCharts[number], spanClass: string) =>
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

  const renderBar = (bar: typeof bars[number], spanClass: string) =>
    bar ? (
      <HorizontalBarPanel
        key={bar.panel.title}
        title={bar.panel.title}
        subtitle={bar.panel.subtitle}
        guide={bar.panel.guide}
        items={bar.items}
        className={spanClass}
        styles={styles}
      />
    ) : null;

  // 「节点压力排行」为 bespoke 取数:config-driven 核心无法表达按 node_name 的动态 TopN,
  // 故复用实例/时间上下文,自行发 topk(by node_name) 查询并解析为 BarList(照搬 postgresql dbname TopN)。
  const { idValues, timeValues, isDashboardMode } = dashboard;
  const [topNode, setTopNode] = useState<Record<string, BarItem[]>>({});
  const idValuesKey = JSON.stringify(idValues);
  const timeKey = JSON.stringify(timeValues);

  useEffect(() => {
    if (!isDashboardMode) {
      setTopNode({});
      return;
    }
    let active = true;
    runWithConcurrency(ES_TOP_NODE_QUERIES, TOP_NODE_CONCURRENCY, async (q) =>
      getInstanceQuery(buildSearchParams(q.query, q.unit, idValues, instanceIdKeys, timeValues))
        .then((res: any) => [q.key, topNodeBars(res, q.unit, q.color)] as const)
        .catch(() => [q.key, [] as BarItem[]] as const)
    ).then((entries) => {
      if (active) {
        setTopNode(Object.fromEntries(entries));
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
          <KpiSection
            dashboard={dashboard}
            summaryCards={summaryCards}
            extraCards={healthCard ? <ClusterHealthCard prepared={healthCard} styles={styles} /> : undefined}
            styles={styles}
          />

          {/* 线程池队列 + 熔断器触发 两张折线同行 span6 + span6 = 12 */}
          <div className={styles.sectionLabel}>线程池与熔断</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(threadQueueChart, styles.span6)}
            {renderChart(breakerTrigChart, styles.span6)}
          </FlexiblePanelSection>

          {/* 节点压力排行:按 node_name 的 topk/bottomk,HorizontalBarPanel × span4 = 12 */}
          <div className={styles.sectionLabel}>节点压力排行</div>
          <section className={styles.dashboardSection}>
            <div className={styles.sectionGrid}>
              {ES_TOP_NODE_QUERIES.map((q) => (
                <HorizontalBarPanel
                  key={q.key}
                  styles={styles}
                  className={`${styles.panel} ${styles.span4}`}
                  title={<TitleWithGuide styles={styles} title={q.title} items={q.guide} className={styles.panelTitleWithGuide} />}
                  items={topNode[q.key] || []}
                />
              ))}
            </div>
          </section>

          {/* 资源使用率 + GC 耗时趋势 两张折线同行 span6 + span6 = 12 */}
          <div className={styles.sectionLabel}>资源与 GC</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(resourceChart, styles.span6)}
            {renderChart(gcChart, styles.span6)}
          </FlexiblePanelSection>

          {/* HTTP 新建连接 + 线程池压力 + 熔断器热点 同行 span4 × 3 = 12 */}
          <div className={styles.sectionLabel}>流量与连接</div>
          <FlexiblePanelSection styles={styles}>
            {renderChart(httpChart, styles.span4)}
            {renderBar(threadPoolBar, styles.span4)}
            {renderBar(breakerBar, styles.span4)}
          </FlexiblePanelSection>

          <DetailSection detailPanels={dashboard.detailPanels} styles={styles} />
        </>
      }
    />
  );
}
