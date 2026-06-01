'use client';

/**
 * Shared layout components for unified dashboards.
 *
 * All "simple" dashboards (MSSQL, Nginx, PostgreSQL, Elasticsearch, …) share
 * the same page shell, KPI grid, chart sections, and detail panels. These
 * components eliminate copy-paste boilerplate while keeping each dashboard's
 * data-filtering logic (titles arrays, span overrides) in its own file.
 */

import React, { useMemo } from 'react';
import {
  ApiOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  NodeIndexOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import MetricViews from '@/app/monitor/components/metric-views';
import {
  CollectionStatusCard,
  DashboardInstanceCard,
  DashboardPageHeader,
  HorizontalBarPanel,
  RingChartPanel,
  StatCard,
  TitleWithGuide,
  TrendChartPanel
} from '../../shared/widgets';
import {
  PreparedSummaryCard,
  PreparedChartPanel,
  PreparedRingPanel,
  PreparedBarPanel,
  PreparedDetailPanel,
  SummaryCardConfig,
  useSimpleDashboardData
} from './simple-dashboard-core';

// ─── Icon helper ─────────────────────────────────────────────────────────────

export const getIcon = (type: SummaryCardConfig['icon']): React.ReactNode => {
  const iconMap: Record<string, React.ReactNode> = {
    api: <ApiOutlined />,
    clock: <ClockCircleOutlined />,
    database: <DatabaseOutlined />,
    node: <NodeIndexOutlined />,
    thunder: <ThunderboltOutlined />
  };
  return iconMap[type] ?? <DatabaseOutlined />;
};

// ─── Panel-filtering hook ─────────────────────────────────────────────────────

const pickDefined = <T,>(items: Array<T | undefined>): T[] =>
  items.filter((item): item is T => Boolean(item));

/**
 * Filters prepared panels by an ordered list of titles, preserving order.
 * Panels not found in the list are omitted; extra entries in the list are
 * silently skipped rather than throwing.
 */
export function useFilteredPanels<T extends { title: string }>(
  allPanels: Array<{ title: T } | { card: T } | { chart: T } | { panel: T }>,
  titles: string[]
): typeof allPanels {
  return useMemo(
    () =>
      pickDefined(
        titles.map((title) =>
          (allPanels as Array<Record<string, unknown>>).find(
            (item) =>
              (item.card as T)?.title === title ||
              (item.chart as T)?.title === title ||
              (item.panel as T)?.title === title
          )
        )
      ) as typeof allPanels,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allPanels, titles.join(',')]
  );
}

// Typed convenience overloads ---

export function useFilteredSummaryCards(
  all: PreparedSummaryCard[],
  titles: string[]
): PreparedSummaryCard[] {
  return useMemo(
    () => pickDefined(titles.map((t) => all.find((c) => c.card.title === t))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, titles.join(',')]
  );
}

export function useFilteredChartPanels(
  all: PreparedChartPanel[],
  titles: string[]
): PreparedChartPanel[] {
  return useMemo(
    () => pickDefined(titles.map((t) => all.find((c) => c.chart.title === t))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, titles.join(',')]
  );
}

export function useFilteredRingPanels(
  all: PreparedRingPanel[],
  titles: string[]
): PreparedRingPanel[] {
  return useMemo(
    () => pickDefined(titles.map((t) => all.find((p) => p.panel.title === t))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, titles.join(',')]
  );
}

export function useFilteredBarPanels(
  all: PreparedBarPanel[],
  titles: string[]
): PreparedBarPanel[] {
  return useMemo(
    () => pickDefined(titles.map((t) => all.find((p) => p.panel.title === t))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, titles.join(',')]
  );
}

// ─── Shared style type ────────────────────────────────────────────────────────

export type DashboardStyles = Record<string, string>;

// ─── KpiSection ──────────────────────────────────────────────────────────────

export interface KpiSectionProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  summaryCards: PreparedSummaryCard[];
  /** Extra cards rendered between CollectionStatusCard and the StatCards. */
  extraCards?: React.ReactNode;
  /** Override the grid column count (default: summaryCards.length + 1). */
  kpiCols?: number;
  styles: DashboardStyles;
}

export const KpiSection = ({
  dashboard,
  summaryCards,
  extraCards,
  kpiCols,
  styles
}: KpiSectionProps) => {
  const extraCount = React.Children.count(extraCards);
  const cols = kpiCols ?? summaryCards.length + 1 + extraCount;

  return (
    <section
      className={styles.kpiGrid}
      style={{ '--kpi-cols': cols } as React.CSSProperties}
    >
      <CollectionStatusCard
        status={dashboard.collectionStatus}
        timeline={dashboard.collectionStatusTimeline}
        guideItems={[
          {
            label: '采集状态',
            detail: `展示最近一段时间内该 ${dashboard.objectFallbackName} 实例监控采集是否正常、缺失或异常。`
          },
          {
            label: '状态时间线',
            detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。'
          }
        ]}
        styles={styles}
      />
      {extraCards}
      {summaryCards.map(({ card, mainValue, valueColor, compare, footerItems, trendData, noDataType }) => {
        const isUptime = card.isUptimeCard;
        const uptimeTone = noDataType === 'error' || mainValue.value === '--' ? 'empty' : 'success';

        return (
          <StatCard
            key={card.title}
            title={<TitleWithGuide title={card.title} items={card.guide} styles={styles} />}
            value={mainValue.value}
            unit={mainValue.unit}
            icon={getIcon(card.icon)}
            iconStyle={{ background: `${valueColor ?? card.color}1f`, color: valueColor ?? card.color }}
            color={valueColor ?? card.color}
            footer={footerItems.map((item) => (
              <span key={item.label}>{item.label} {item.value}</span>
            ))}
            compare={compare}
            trendData={trendData}
            hideTrend={card.hideTrend}
            noDataType={noDataType}
            className={isUptime ? styles.statCardRelaxed : undefined}
            bodyClassName={isUptime ? styles.statBodyRelaxed : undefined}
            extra={isUptime ? (
              <div className={`${styles.uptimeStatus} ${styles[`uptimeStatus${uptimeTone === 'success' ? 'Success' : 'Empty'}`]}`}>
                <span className={styles.uptimeStatusDot} />
                <div className={styles.uptimeStatusMainWrap}>
                  <span className={styles.uptimeStatusMain}>
                    {uptimeTone === 'success' ? '运行正常' : '暂无数据'}
                  </span>
                </div>
              </div>
            ) : undefined}
            styles={styles}
          />
        );
      })}
    </section>
  );
};

// ─── TrendSection ─────────────────────────────────────────────────────────────

export interface TrendSectionProps {
  charts: PreparedChartPanel[];
  onXRangeChange: ReturnType<typeof useSimpleDashboardData>['onXRangeChange'];
  /** Whether metrics are still loading — forwarded to EChartsLineChart to show Spin vs Empty. */
  loading?: boolean;
  /**
   * Map from chart index → CSS span class name.
   * Defaults to `styles.span4` for every chart when unspecified.
   * Pass `(i, total) => styles.span6` to override per-item.
   */
  spanClass?: (index: number, total: number) => string;
  styles: DashboardStyles;
}

export const TrendSection = ({
  charts,
  onXRangeChange,
  loading = false,
  spanClass,
  styles
}: TrendSectionProps) => {
  if (charts.length === 0) return null;
  return (
    <section className={styles.dashboardSection}>
      <div className={styles.sectionGrid}>
        {charts.map(({ chart, data, metric, unit, legends, seriesStyles }, index) => (
          <TrendChartPanel
            key={chart.title}
            title={chart.title}
            subtitle={chart.subtitle}
            guide={chart.guide}
            legends={legends}
            data={data}
            metric={metric}
            unit={unit}
            loading={loading}
            seriesStyles={seriesStyles}
            onXRangeChange={onXRangeChange}
            className={`${styles.panel} ${spanClass ? spanClass(index, charts.length) : styles.span4}`}
            styles={styles}
          />
        ))}
      </div>
    </section>
  );
};

// ─── InsightSection ──────────────────────────────────────────────────────────

/**
 * Derive a sensible default span class so that panels fill the 12-column grid
 * without leaving empty columns.
 *
 * Total panels → span per panel:
 *   1  → span12
 *   2  → span6
 *   3  → span4
 *   4  → span3
 *   6  → span4 (2 rows of 3)
 *   otherwise → span4 (wraps naturally)
 */
const autoSpan = (total: number, styles: DashboardStyles): string => {
  if (total === 1) return styles.span12;
  if (total === 2) return styles.span6;
  if (total === 4) return styles.span3;
  return styles.span4; // 3, 6, or other multiples of 3
};

export interface InsightSectionProps {
  rings: PreparedRingPanel[];
  bars: PreparedBarPanel[];
  ringSpanClass?: (index: number, total: number) => string;
  barSpanClass?: (index: number, total: number) => string;
  styles: DashboardStyles;
}

export const InsightSection = ({
  rings,
  bars,
  ringSpanClass,
  barSpanClass,
  styles
}: InsightSectionProps) => {
  if (rings.length === 0 && bars.length === 0) return null;
  const total = rings.length + bars.length;
  const defaultSpan = autoSpan(total, styles);
  return (
    <section className={styles.dashboardSection}>
      <div className={styles.sectionGrid}>
        {rings.map(({ panel, data, centerValue }, index) => (
          <RingChartPanel
            key={panel.title}
            title={panel.title}
            subtitle={panel.subtitle}
            guide={panel.guide}
            data={data}
            centerValue={centerValue}
            centerCaption={panel.centerCaption}
            className={`${styles.panel} ${ringSpanClass ? ringSpanClass(index, rings.length) : defaultSpan}`}
            styles={styles}
          />
        ))}
        {bars.map(({ panel, items }, index) => (
          <HorizontalBarPanel
            key={panel.title}
            title={panel.title}
            subtitle={panel.subtitle}
            guide={panel.guide}
            items={items}
            className={`${styles.panel} ${barSpanClass ? barSpanClass(index, bars.length) : defaultSpan}`}
            styles={styles}
          />
        ))}
      </div>
    </section>
  );
};

// ─── DetailSection ────────────────────────────────────────────────────────────

export interface DetailSectionProps {
  detailPanels: PreparedDetailPanel[];
  styles: DashboardStyles;
}

export const DetailSection = ({ detailPanels, styles }: DetailSectionProps) => {
  if (detailPanels.length === 0) return null;
  return (
    <section className={styles.detailGridBalanced}>
      {detailPanels.map(({ panel, rows, hasData }) => (
        <div key={panel.title} className={styles.panel}>
          <h3 className={styles.panelTitle}>{panel.title}</h3>
          <div className={styles.panelSubTitle}>{panel.subtitle}</div>
          {hasData ? (
            rows.map((row) => (
              <div key={row.label} className={styles.detailMetricRow}>
                <span>{row.label}</span>
                <span className={styles.detailMetricValue}>{row.value}</span>
              </div>
            ))
          ) : (
            <div className={styles.detailEmpty}>当前时间范围内暂无可展示详情</div>
          )}
        </div>
      ))}
    </section>
  );
};

// ─── MetricsSection ───────────────────────────────────────────────────────────

export interface MetricsSectionProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  styles: DashboardStyles;
}

export const MetricsSection = ({ dashboard, styles }: MetricsSectionProps) => (
  <div className={styles.metricsMode}>
    <div className={`${styles.panel} ${styles.fullPanel}`}>
      <div className={styles.sectionHeading}>
        <h3 className={styles.panelTitle}>
          <TitleWithGuide
            title="监控指标全量"
            items={[{ label: '监控指标全景', detail: '承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' }]}
            styles={styles}
          />
        </h3>
      </div>
      <MetricViews
        monitorObjectId={dashboard.monitorObjectId}
        monitorObjectName={dashboard.monitorObjectName}
        instanceId={dashboard.instanceId}
        instanceName={dashboard.resolvedInstanceName}
        idValues={dashboard.idValues}
        externalTimeValues={dashboard.timeValues}
        externalTimeDefaultValue={dashboard.timeDefaultValue}
        externalFrequence={dashboard.frequence}
        externalRefreshSignal={dashboard.metricsRefreshSignal}
        hideTimeSelector
        onExternalXRangeChange={dashboard.onXRangeChange}
      />
    </div>
  </div>
);

// ─── DashboardShell ───────────────────────────────────────────────────────────

export interface DashboardShellProps {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  /** Dashboard content (only shown in dashboard display mode). */
  dashboardContent: React.ReactNode;
  styles: DashboardStyles;
}

/**
 * Top-level shell: page wrapper, header controls, instance selector, and the
 * dashboard ↔ metrics mode toggle.  Pass your layout as `dashboardContent`.
 */
export const DashboardShell = ({
  dashboard,
  dashboardContent,
  styles
}: DashboardShellProps) => (
  <div className={styles.page}>
    <div className={styles.shell}>
      <div className={styles.pageHeader}>
        <DashboardPageHeader
          title={dashboard.pageTitle}
          displayMode={dashboard.displayMode}
          onDisplayModeChange={dashboard.setDisplayMode}
          timeDefaultValue={dashboard.timeDefaultValue}
          onTimeChange={dashboard.onTimeChange}
          onFrequenceChange={dashboard.setFrequence}
          onRefresh={dashboard.onRefresh}
          onBack={dashboard.onBack}
          styles={styles}
        />
        <DashboardInstanceCard
          instanceName={dashboard.resolvedInstanceName}
          metaItems={dashboard.objectMetaItems.map((item, index) => (
            <span key={index} className={styles.instanceMetaInline}>{item}</span>
          ))}
          icon={<DatabaseOutlined />}
          selectorValue={dashboard.instanceSelectValue}
          selectorLoading={dashboard.instanceLoading}
          selectorOptions={dashboard.instanceSelectOptions}
          onInstanceChange={dashboard.onInstanceChange}
          selectorPlaceholder={
            dashboard.resolvedInstanceName !== '--' ? dashboard.resolvedInstanceName : '选择实例'
          }
          selectorTitle={dashboard.currentInstanceLabel}
          isDashboardMode={dashboard.isDashboardMode}
          styles={styles}
        />
      </div>

      {dashboard.displayMode === 'dashboard' ? (
        <>{dashboardContent}</>
      ) : (
        <MetricsSection dashboard={dashboard} styles={styles} />
      )}
    </div>
  </div>
);
