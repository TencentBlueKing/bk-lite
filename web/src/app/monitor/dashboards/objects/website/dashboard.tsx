'use client';

import React, { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Tabs } from 'antd';
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
import { RingChartPanel, TrendChartPanel } from '../../shared/widgets';
import { WEBSITE_DASHBOARD_CONFIG } from './config';
import { WebsiteDeepAnalysis } from './website-deep-analysis';
import styles from './index.module.scss';

const SUMMARY_TITLES = ['探测成功率', '平均响应时间'];
const PRIMARY_CHART_TITLES = ['探测成功率趋势', '响应时间趋势'];
const RING_TITLES = ['探测结果分布', '状态码分布'];

export default function WebsiteDashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const dashboard = useSimpleDashboardData(WEBSITE_DASHBOARD_CONFIG);

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

  const summaryCards = useFilteredSummaryCards(dashboard.summaryCards, SUMMARY_TITLES);
  const charts = useFilteredChartPanels(dashboard.chartPanels, PRIMARY_CHART_TITLES);
  const rings = useFilteredRingPanels(dashboard.ringPanels, RING_TITLES);

  const [successChart, responseChart] = charts;
  const [resultCodeRing, statusCodeRing] = rings;

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
      title={activeTab === 'deep' ? '网站深度分析' : dashboard.pageTitle}
      tabsSlot={tabsSlot}
      dashboardContent={
        activeTab === 'deep' ? (
          <WebsiteDeepAnalysis
            dashboard={dashboard}
            styles={styles}
          />
        ) : (
          <>
            <DashboardSectionLabel styles={styles}>健康概览</DashboardSectionLabel>
            <KpiSection dashboard={dashboard} summaryCards={summaryCards} kpiCols={3} styles={styles} />

            <DashboardSectionLabel styles={styles}>趋势</DashboardSectionLabel>
            <FlexiblePanelSection styles={styles}>
              {successChart ? (
                <TrendChartPanel
                  key={successChart.chart.title}
                  title={successChart.chart.title}
                  subtitle={successChart.chart.subtitle}
                  guide={successChart.chart.guide}
                  legends={successChart.legends}
                  data={successChart.data}
                  metric={successChart.metric}
                  unit={successChart.unit}
                  loading={dashboard.loading}
                  seriesStyles={successChart.seriesStyles}
                  onXRangeChange={dashboard.onXRangeChange}
                  className={`${styles.span6} ${styles.compactTrend}`}
                  styles={styles}
                />
              ) : null}
              {responseChart ? (
                <TrendChartPanel
                  key={responseChart.chart.title}
                  title={responseChart.chart.title}
                  subtitle={responseChart.chart.subtitle}
                  guide={responseChart.chart.guide}
                  legends={responseChart.legends}
                  data={responseChart.data}
                  metric={responseChart.metric}
                  unit={responseChart.unit}
                  loading={dashboard.loading}
                  seriesStyles={responseChart.seriesStyles}
                  onXRangeChange={dashboard.onXRangeChange}
                  className={`${styles.span6} ${styles.compactTrend}`}
                  styles={styles}
                />
              ) : null}
            </FlexiblePanelSection>

            <DashboardSectionLabel styles={styles}>失败归因</DashboardSectionLabel>
            <FlexiblePanelSection styles={styles}>
              {resultCodeRing ? (
                <RingChartPanel
                  key={resultCodeRing.panel.title}
                  title={resultCodeRing.panel.title}
                  subtitle={resultCodeRing.panel.subtitle}
                  guide={resultCodeRing.panel.guide}
                  data={resultCodeRing.data}
                  centerValue={resultCodeRing.centerValue}
                  centerCaption={resultCodeRing.panel.centerCaption}
                  isEmpty={resultCodeRing.isEmpty}
                  emptyDescription={resultCodeRing.emptyDescription}
                  className={styles.span6}
                  styles={styles}
                />
              ) : null}
              {statusCodeRing ? (
                <RingChartPanel
                  key={statusCodeRing.panel.title}
                  title={statusCodeRing.panel.title}
                  subtitle={statusCodeRing.panel.subtitle}
                  guide={statusCodeRing.panel.guide}
                  data={statusCodeRing.data}
                  centerValue={statusCodeRing.centerValue}
                  centerCaption={statusCodeRing.panel.centerCaption}
                  isEmpty={statusCodeRing.isEmpty}
                  emptyDescription={statusCodeRing.emptyDescription}
                  className={styles.span6}
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
