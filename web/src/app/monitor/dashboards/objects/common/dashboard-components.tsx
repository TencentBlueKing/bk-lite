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
import {
  HealthIcon,
  MemoryIcon,
  UnackedIcon,
  BacklogIcon,
  PublishIcon
} from '../../shared/widgets/metric-icons';
import MetricViews from '@/app/monitor/components/metric-views';
import {
  CollectionStatusCard,
  DashboardInstanceCard,
  DashboardPageHeader,
  HorizontalBarPanel,
  MiniTrendChart,
  RingChartPanel,
  StatCard,
  TitleWithGuide,
  TrendChartPanel
} from '../../shared/widgets';
import { GuideItem } from '../../shared/types';
import {
  PreparedSummaryCard,
  PreparedChartPanel,
  PreparedRingPanel,
  PreparedBarPanel,
  PreparedStatusPanel,
  PreparedDetailPanel,
  DetailRowViz,
  SummaryCardConfig,
  useSimpleDashboardData
} from './simple-dashboard-core';
import { ChartData } from '@/app/monitor/types';

// ─── Icon helper ─────────────────────────────────────────────────────────────

export const getIcon = (type: SummaryCardConfig['icon']): React.ReactNode => {
  const iconMap: Record<string, React.ReactNode> = {
    api: <ApiOutlined />,
    clock: <ClockCircleOutlined />,
    database: <DatabaseOutlined />,
    node: <NodeIndexOutlined />,
    thunder: <ThunderboltOutlined />,
    // Bespoke duotone metric icons (KPI cards)
    health: <HealthIcon />,
    memory: <MemoryIcon />,
    unacked: <UnackedIcon />,
    backlog: <BacklogIcon />,
    publish: <PublishIcon />
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

export function useFilteredStatusPanels(
  all: PreparedStatusPanel[],
  titles: string[]
): PreparedStatusPanel[] {
  return useMemo(
    () => pickDefined(titles.map((t) => all.find((p) => p.panel.title === t))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, titles.join(',')]
  );
}

export function useFilteredDetailPanels(
  all: PreparedDetailPanel[],
  titles: string[]
): PreparedDetailPanel[] {
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
  const cols = Math.min(kpiCols ?? summaryCards.length + 1 + extraCount, 6);

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
      {summaryCards.map(({ card, mainValue, valueColor, compare, footerItems, trendData, noDataType, uptimeState }) => {
        const isUptime = card.isUptimeCard;
        // 运行时长卡统一样式:不画折线,只显示「所选时间范围内是否发生重启」(运行正常 / 期间有重启 / 状态未知)。
        const uptimeToneSuffix =
          uptimeState?.tone === 'warning' ? 'Warning' : uptimeState?.tone === 'success' ? 'Success' : 'Empty';

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
            compareFavorableDirection={card.compareFavorableDirection}
            trendData={trendData}
            hideTrend={isUptime ? true : card.hideTrend}
            noDataType={noDataType}
            className={isUptime ? styles.statCardRelaxed : undefined}
            bodyClassName={isUptime ? styles.statBodyRelaxed : undefined}
            extra={isUptime ? (
              <div className={`${styles.uptimeStatus} ${styles[`uptimeStatus${uptimeToneSuffix}`]}`}>
                <span className={styles.uptimeStatusDot} />
                <div className={styles.uptimeStatusMainWrap}>
                  <span className={styles.uptimeStatusMain}>
                    {uptimeState?.label ?? '状态未知'}
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

const autoTrendSpan = (total: number, styles: DashboardStyles): string => {
  if (total === 1) return styles.span12;
  if (total === 2) return styles.span6;
  return styles.span4;
};

export const TrendSection = ({
  charts,
  onXRangeChange,
  loading = false,
  spanClass,
  styles
}: TrendSectionProps) => {
  if (charts.length === 0) return null;
  const defaultSpan = autoTrendSpan(charts.length, styles);
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
            className={`${styles.panel} ${spanClass ? spanClass(index, charts.length) : defaultSpan}`}
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
  rings?: PreparedRingPanel[];
  bars: PreparedBarPanel[];
  ringSpanClass?: (index: number, total: number) => string;
  barSpanClass?: (index: number, total: number) => string;
  styles: DashboardStyles;
}

export const InsightSection = ({
  rings = [],
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
        {rings.map(({ panel, data, centerValue, isEmpty }, index) => (
          <RingChartPanel
            key={panel.title}
            title={panel.title}
            subtitle={panel.subtitle}
            guide={panel.guide}
            data={data}
            centerValue={centerValue}
            centerCaption={panel.centerCaption}
            isEmpty={isEmpty}
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

const DETAIL_TONE_COLORS: Record<'error' | 'warning' | 'normal', string> = {
  error: '#ff4d4f',
  warning: '#faad14',
  normal: '#2f6bff'
};

export interface DetailMetricRowProps {
  label: string;
  value: React.ReactNode;
  /** spark=速率/计数迷你趋势；bar=百分比进度条；none=纯数值 */
  viz?: DetailRowViz;
  /** spark 用:完整时序 */
  trend?: ChartData[];
  /** bar 用:当前值(0–100) */
  barValue?: number;
  tone?: 'error' | 'warning' | 'normal';
  /** 枚举/状态行:状态语义色(前置色点 + 文案着色),优先于 tone */
  statusColor?: string;
  /** sparkline 配色:取该指标语义色,与 KPI/趋势/异常信号条统一;缺省回退 tone 色 */
  color?: string;
  /** 提供时在标签后渲染 (i) 帮助,悬停显示口径说明(术语行如「用户断言」「游标超时数」)。 */
  guide?: GuideItem[];
  styles: DashboardStyles;
}

/**
 * 详情面板单行:标签 · 缩略图 · 数值。共享给 DetailPanelCard 以及自定义仪表盘
 * (如 MongoDB)的详情面板,确保实时数值的缩略图渲染口径一致。
 */
export const DetailMetricRow = ({
  label,
  value,
  viz = 'none',
  trend = [],
  barValue = 0,
  tone = 'normal',
  statusColor,
  color,
  guide,
  styles
}: DetailMetricRowProps) => {
  const toneColor = DETAIL_TONE_COLORS[tone];
  // sparkline/进度条配色:优先指标语义色(与 KPI/趋势/异常信号条同源),回退 tone 色。
  const vizColor = color ?? toneColor;
  // 数值文字颜色:枚举状态色优先,其次手动 tone(error/warning),否则默认。
  const valueColor = statusColor ?? (tone === 'normal' ? undefined : toneColor);
  return (
    <div className={styles.detailMetricRow}>
      {guide && guide.length > 0 ? (
        <TitleWithGuide title={label} items={guide} className={styles.detailMetricLabel} styles={styles} />
      ) : (
        <span className={styles.detailMetricLabel}>{label}</span>
      )}
      {/* 缩略图列始终渲染(空行也占位),保证三列网格对齐:标签 · 缩略图 · 数值。 */}
      <span className={styles.detailRowViz}>
        {viz === 'spark' && <MiniTrendChart data={trend} color={vizColor} styles={styles} />}
        {viz === 'bar' && (
          <span className={styles.detailBar}>
            <span className={styles.detailBarFill} style={{ width: `${barValue}%`, background: vizColor }} />
          </span>
        )}
      </span>
      <span className={styles.detailMetricValue} style={valueColor ? { color: valueColor } : undefined}>
        {statusColor && <span className={styles.detailStatusDot} style={{ background: statusColor }} />}
        {value}
      </span>
    </div>
  );
};

export interface DetailPanelCardProps {
  detailPanel: PreparedDetailPanel;
  className?: string;
  styles: DashboardStyles;
}

export const DetailPanelCard = ({ detailPanel, className, styles }: DetailPanelCardProps) => {
  const { panel, rows, hasData } = detailPanel;

  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
      <h3 className={styles.panelTitle}>{panel.title}</h3>
      <div className={styles.panelSubTitle}>{panel.subtitle}</div>
      {hasData ? (
        <div className={styles.detailRowsFill}>
          {rows.map((row) => (
            <DetailMetricRow
              key={row.label}
              label={row.label}
              value={row.value}
              viz={row.viz}
              trend={row.trend}
              barValue={row.barValue}
              tone={row.tone}
              statusColor={row.statusColor}
              color={row.color}
              styles={styles}
            />
          ))}
        </div>
      ) : (
        <div className={styles.detailEmpty}>当前时间范围内暂无可展示详情</div>
      )}
    </div>
  );
};

export interface FlexiblePanelSectionProps {
  children: React.ReactNode;
  styles: DashboardStyles;
}

export const FlexiblePanelSection = ({ children, styles }: FlexiblePanelSectionProps) => {
  if (!React.Children.count(children)) return null;

  return (
    <section className={styles.dashboardSection}>
      <div className={styles.sectionGrid}>{children}</div>
    </section>
  );
};

export interface DetailSectionProps {
  detailPanels: PreparedDetailPanel[];
  styles: DashboardStyles;
}

export const DetailSection = ({ detailPanels, styles }: DetailSectionProps) => {
  if (detailPanels.length === 0) return null;
  return (
    <section className={styles.detailGridBalanced}>
      {detailPanels.map((detailPanel) => (
        <DetailPanelCard
          key={detailPanel.panel.title}
          detailPanel={detailPanel}
          styles={styles}
        />
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
        collectionInterval={dashboard.currentInstanceInterval}
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
  /** 可选品牌标签（如 'Cisco'）：共享对象仪表盘按实例品牌在头部高亮显示，便于辨认当前盘属于哪个品牌。 */
  brandLabel?: string;
  styles: DashboardStyles;
}

/**
 * Top-level shell: page wrapper, header controls, instance selector, and the
 * dashboard ↔ metrics mode toggle.  Pass your layout as `dashboardContent`.
 */
export const DashboardShell = ({
  dashboard,
  dashboardContent,
  brandLabel,
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
          showTimeSelector={false}
          styles={styles}
        />
        <DashboardInstanceCard
          instanceName={dashboard.resolvedInstanceName}
          metaItems={[
            ...(brandLabel
              ? [
                <span key="brand" className={styles.instanceMetaInline}>{brandLabel}</span>
              ]
              : []),
            ...dashboard.objectMetaItems.map((item, index) => (
              <span key={index} className={styles.instanceMetaInline}>{item}</span>
            ))
          ]}
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
          timeSelectorProps={{
            timeDefaultValue: dashboard.timeDefaultValue,
            onTimeChange: dashboard.onTimeChange,
            onFrequenceChange: dashboard.setFrequence,
            onRefresh: dashboard.onRefresh
          }}
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
