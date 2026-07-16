import React from 'react';
import dayjs from 'dayjs';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import type { Meta, StoryObj } from '@storybook/react';
import {
  BacklogIcon,
  CollectionStatusCard,
  DashboardPageHeader,
  DashboardPanel,
  DashboardInstanceCard,
  DetailMetricRow,
  DetailPanel,
  DetailPanelCard,
  HealthIcon,
  HorizontalBarPanel,
  InstanceSelector,
  MemoryIcon,
  PublishIcon,
  RingChartPanel,
  StackedBarPanel,
  StatCard,
  TitleWithGuide,
  TrendChartPanel,
  UnackedIcon,
  type CollectionStatusCardStyles,
  type DashboardPageHeaderStyles,
  type DashboardPanelStyles,
  type DashboardInstanceCardStyles,
  type DetailMetricRowStyles,
  type DetailPanelCardStyles,
  type DetailPanelStyles,
  type GuideTooltipStyles,
  type HorizontalBarPanelStyles,
  type InstanceSelectorStyles,
  type RingChartPanelStyles,
  type StackedBarPanelStyles,
  type StatCardStyles,
  type TrendChartPanelStyles,
} from '@/components/monitor-dashboard-widgets';
import type { ChartData, MetricItem } from '@/components/monitor-dashboard-widgets/types';

const statStyles: StatCardStyles = {
  statCard:
    'flex min-h-[188px] flex-col overflow-hidden rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]',
  statHeader: 'flex items-start justify-between gap-3',
  statLabel: 'text-[15px] font-semibold leading-[1.35] text-[var(--color-text-1)]',
  statIcon:
    'flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-[var(--color-fill-1)] text-[18px]',
  statBody: 'mt-4 flex min-h-0 flex-col gap-2',
  statValue:
    'inline-flex min-h-[40px] flex-wrap items-baseline gap-1 text-[32px] font-semibold leading-none text-[var(--color-text-1)]',
  statUnit: 'text-[14px] font-medium text-[var(--color-text-3)]',
  statCompare:
    'flex min-h-[20px] flex-wrap items-center gap-2 text-[13px] font-medium text-[var(--color-text-2)]',
  statCompareFlat: '',
  statComparePositive: '',
  statCompareNegative: '',
  statCompareLabel: 'text-[var(--color-text-3)]',
  statCompareValue: 'inline-flex items-center gap-1',
  statMeta:
    'flex min-h-[22px] flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--color-text-2)]',
  statExtra: 'mt-auto pt-3',
  miniTrend: 'mt-auto h-[56px] overflow-hidden rounded-[10px] pt-3',
  miniTrendPlaceholder: 'h-full w-full rounded-[10px] bg-[var(--color-fill-1)]',
};

const trendStyles: TrendChartPanelStyles = {
  panel:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeader: 'mb-4',
  chartPanelHeader: 'flex items-start justify-between gap-4',
  panelHeading: 'flex min-w-0 flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  chartHeaderTitle: '',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  chartHeaderSubTitle: '',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
  chartLegend:
    'flex flex-wrap items-center justify-end gap-x-4 gap-y-2 text-[12px] text-[var(--color-text-2)]',
  chartLegendHeader: '',
  chartLegendItem: 'inline-flex items-center gap-2',
  chartLegendDot: 'inline-block h-2.5 w-2.5 rounded-full border',
  chartLegendDash: 'border-dashed',
  chartWrap:
    'rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3',
};

const ringStyles: RingChartPanelStyles = {
  panel:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeader: 'mb-4',
  panelHeading: 'flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
  ringCard: 'grid grid-cols-[220px_minmax(0,1fr)] gap-6',
  ringChartWrap:
    'relative flex h-[220px] items-center justify-center rounded-[16px] bg-[var(--color-fill-1)]',
  ringChartCanvas: 'h-[180px] w-[180px]',
  ringCenter: 'text-center',
  ringCenterOverlay:
    'pointer-events-none absolute inset-0 flex flex-col items-center justify-center',
  ringValue: 'text-[28px] font-semibold text-[var(--color-text-1)]',
  ringCaption: 'text-[12px] text-[var(--color-text-3)]',
  ringInfoPanel:
    'rounded-[16px] bg-[var(--color-fill-1)] px-4 py-4 text-[13px]',
  metricList: 'space-y-3',
  metricRow: 'flex items-center justify-between gap-3',
  metricRowPercentOnly: '',
  metricKey: 'min-w-0 flex-1',
  metricLabelGroup: 'flex items-center gap-2 min-w-0',
  metricDot: 'h-2.5 w-2.5 rounded-full',
  metricName: 'truncate text-[var(--color-text-2)]',
  metricValueGroup: 'flex items-center gap-2 text-[var(--color-text-1)]',
  metricPercent: 'font-semibold',
  metricCount: 'text-[var(--color-text-3)]',
};

const instanceStyles: DashboardInstanceCardStyles = {
  instanceCard:
    'flex flex-wrap items-center justify-between gap-4 rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5',
  instanceCardFull: 'items-start',
  instanceMain: 'flex min-w-0 items-center gap-4',
  instanceIcon:
    'flex h-12 w-12 items-center justify-center rounded-[14px] bg-[var(--color-fill-1)] text-[20px] text-[var(--color-primary)]',
  instanceInfo: 'min-w-0',
  meta: 'flex flex-wrap items-center gap-2 text-[13px] text-[var(--color-text-2)]',
  instanceName: 'text-[18px] font-semibold text-[var(--color-text-1)]',
  instanceMetaDivider: 'text-[var(--color-border-2)]',
  instanceActions: 'flex flex-wrap items-center gap-3',
  inlineInstanceSelector:
    'min-w-[240px] rounded-[12px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-2',
  instanceSelectorLabel: 'text-[13px] text-[var(--color-text-3)]',
  toolbarTimeSelector: 'min-w-[458px]',
};

const instanceSelectorStyles: InstanceSelectorStyles = {
  inlineInstanceSelector:
    'min-w-[260px] rounded-[12px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-2 shadow-[0_2px_12px_rgba(15,23,42,0.03)]',
  instanceSelectorLabel: 'text-[13px] font-medium text-[var(--color-text-3)]',
};

const guideTooltipStyles: GuideTooltipStyles = {
  titleWithGuide:
    'inline-flex items-center gap-2 text-[14px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const collectionStatusStyles: CollectionStatusCardStyles = {
  statCard:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  collectionStatusCard: 'min-h-[244px]',
  collectionStatusHeader: 'mb-4',
  statLabel: 'text-[12px] text-[var(--color-text-3)]',
  statTitleWithGuide:
    'inline-flex items-center gap-2 text-[14px] font-semibold text-[var(--color-text-1)]',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[14px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
  collectionStatusBody: 'space-y-4',
  collectionStatusValue: 'text-[30px] font-semibold leading-none',
  collectionStatusValueSuccess: 'text-[var(--color-success)]',
  collectionStatusValueWarning: 'text-[#f59e0b]',
  collectionStatusValueError: 'text-[#f04438]',
  collectionStatusValueEmpty: 'text-[var(--color-text-3)]',
  collectionStatusTimelineBlock:
    'rounded-[14px] bg-[var(--color-fill-1)] px-4 py-3',
  collectionStatusTimelineTitle:
    'mb-2 text-[12px] font-medium text-[var(--color-text-3)]',
  collectionStatusTimeline: 'mb-3 flex gap-1.5',
  collectionStatusSegment: 'h-2 flex-1 rounded-full',
  collectionStatusSegmentSuccess: 'bg-[var(--color-success)]',
  collectionStatusSegmentWarning: 'bg-[#f59e0b]',
  collectionStatusSegmentError: 'bg-[#f04438]',
  collectionStatusSegmentEmpty: 'bg-[var(--color-border-2)]',
  collectionStatusTimelineEmpty:
    'rounded-[10px] border border-dashed border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 py-5 text-center text-[12px] text-[var(--color-text-3)]',
  collectionStatusLegend:
    'flex flex-wrap gap-x-3 gap-y-2 text-[11px] text-[var(--color-text-3)]',
  collectionStatusLegendItem: 'inline-flex items-center gap-1.5',
  collectionStatusLegendDot: 'h-2 w-2 rounded-full',
};

const detailMetricRowStyles: DetailMetricRowStyles = {
  detailMetricRow:
    'grid grid-cols-[minmax(96px,140px)_minmax(0,1fr)_auto] items-center gap-3 text-[13px] font-semibold text-[var(--color-text-2)]',
  detailMetricLabel: 'min-w-0 truncate text-[var(--color-text-2)]',
  detailRowViz: 'flex h-[30px] min-w-0 items-center',
  detailBar: 'h-2 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]',
  detailBarFill: 'h-full rounded-full',
  detailMetricValue:
    'justify-self-end whitespace-nowrap text-[15px] font-semibold text-[var(--color-text-1)]',
  detailStatusDot: 'mr-1.5 inline-block h-2 w-2 rounded-full align-middle',
  miniTrendPlaceholder: 'h-full w-full rounded-[8px] bg-[var(--color-fill-1)]',
  titleWithGuide:
    'inline-flex items-center gap-1.5 text-[13px] font-semibold text-[var(--color-text-2)]',
  metricGuideIcon:
    'cursor-help text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const headerStyles: DashboardPageHeaderStyles = {
  pageTitleRow:
    'flex flex-wrap items-center justify-between gap-4 rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5',
  titleBlock: 'min-w-0',
  title: 'm-0 text-[22px] font-semibold text-[var(--color-text-1)]',
  controlsWrap: 'flex flex-wrap items-center gap-3',
  modeTabs:
    'inline-flex items-center rounded-[12px] bg-[var(--color-fill-1)] p-1',
  modeTab:
    'rounded-[10px] px-3 py-1.5 text-[13px] text-[var(--color-text-2)] transition',
  modeTabActive:
    'bg-[var(--color-bg-1)] text-[var(--color-text-1)] shadow-sm',
  toolbarTimeSelector: 'min-w-[458px]',
  toolbarBackBtn: 'shrink-0',
  actionButtons: 'flex items-center',
};

const dashboardPanelStyles: DashboardPanelStyles = {
  panel:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeader: 'mb-4',
  panelHeading: 'flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const detailPanelStyles: DetailPanelStyles = {
  panel: 'rounded-[18px] border border-[var(--color-border-1)] bg-transparent',
  detailCard:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeading: 'mb-4 flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  detailRowsFill: 'space-y-3',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const detailPanelCardStyles: DetailPanelCardStyles = {
  panel:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeading: 'mb-4 flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  detailRowsFill: 'flex flex-col gap-4',
  detailEmpty: 'flex min-h-[72px] items-center text-[14px] text-[var(--color-text-3)]',
  detailMetricRow:
    'grid grid-cols-[minmax(96px,140px)_minmax(0,1fr)_auto] items-center gap-3 text-[13px] font-semibold text-[var(--color-text-2)]',
  detailMetricLabel: 'min-w-0 truncate text-[var(--color-text-2)]',
  detailRowViz: 'flex h-[30px] min-w-0 items-center',
  detailBar: 'h-2 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]',
  detailBarFill: 'h-full rounded-full',
  detailMetricValue:
    'justify-self-end whitespace-nowrap text-[15px] font-semibold text-[var(--color-text-1)]',
  detailStatusDot: 'mr-1.5 inline-block h-2 w-2 rounded-full align-middle',
  miniTrendPlaceholder: 'h-full w-full rounded-[8px] bg-[var(--color-fill-1)]',
  titleWithGuide:
    'inline-flex items-center gap-1.5 text-[13px] font-semibold text-[var(--color-text-2)]',
  metricGuideIcon:
    'cursor-help text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const horizontalBarStyles: HorizontalBarPanelStyles = {
  panel:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeader: 'mb-4',
  panelHeading: 'flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
  bars: 'space-y-3',
  compactBars: '',
  barsFull: '',
  barsTrend: '',
  barRow: 'grid grid-cols-[minmax(0,180px)_1fr_auto] items-center gap-3',
  barRowEmphasis: 'rounded-[12px] bg-[var(--color-fill-1)] px-3 py-2',
  barRowMuted: 'opacity-80',
  barLabel: 'min-w-0 text-[13px] text-[var(--color-text-2)]',
  barTrack: 'h-2 overflow-hidden rounded-full bg-[var(--color-border-2)]',
  barFill: 'h-full rounded-full',
  barSpark: 'h-[28px]',
  barValue: 'text-[13px] font-medium text-[var(--color-text-1)]',
  miniTrendPlaceholder: 'text-[var(--color-text-4)]',
};

const stackedBarStyles: StackedBarPanelStyles = {
  panel:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeader: 'mb-3',
  panelHeading: 'flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const trendData: ChartData[] = [
  { time: 1719302400, value1: 42 },
  { time: 1719306000, value1: 48 },
  { time: 1719309600, value1: 45 },
  { time: 1719313200, value1: 52 },
  { time: 1719316800, value1: 49 },
  { time: 1719320400, value1: 57 },
];

const now = dayjs();
const seriesData = Array.from({ length: 12 }, (_, index) => ({
  time: now.subtract(11 - index, 'minute').unix(),
  value1: 62 + index * 3,
  value2: 48 + index * 2,
  details: {
    [String(now.subtract(11 - index, 'minute').unix())]: [
      { name: 'primary', label: '主序列', value: `${62 + index * 3} ms` },
      { name: 'secondary', label: '辅序列', value: `${48 + index * 2} ms` },
    ],
  },
}));

const metric: MetricItem = {
  id: 1,
  metric_group: 1,
  metric_object: 1,
  name: 'latency',
  type: 'time',
  display_name: 'Latency',
  dimensions: [],
  unit: 'ms',
};

const detailGuideItems = [
  {
    label: '内存详情',
    detail: '用于拆分 RSS、缓存和可回收内存等细项，定位具体压力来源。',
  },
];

const dashboardGuideItems = [
  {
    label: '连接趋势',
    detail: '展示当前连接数与异常连接变化，帮助判断负载峰值是否持续。',
  },
  {
    label: '排查建议',
    detail: '建议结合慢查询和线程状态一起定位连接堆积来源。',
  },
];

const selectorOptions = [
  {
    label: 'mysql-prod-01 / 10.10.1.21',
    value: 'mysql-prod-01',
    searchTokens: ['mysql-prod-01', 'mysql', '10.10.1.21', 'production'],
  },
  {
    label: 'mysql-report-02 / 10.10.1.34',
    value: 'mysql-report-02',
    searchTokens: ['mysql-report-02', 'mysql', '10.10.1.34', 'reporting'],
  },
  {
    label: 'redis-cache-01 / cache-shanghai-a',
    value: 'redis-cache-01',
    searchTokens: ['redis-cache-01', 'redis', 'cache-shanghai-a', 'cache'],
  },
];

const guideItems = [
  {
    label: '连接使用率',
    detail: '当前活跃连接占最大连接数的比例，用于判断连接池是否逼近上限。',
  },
  {
    label: '排查建议',
    detail: '结合连接趋势与慢查询指标一起观察，区分瞬时峰值和持续性拥塞。',
  },
];

const rankingGuideItems = [
  {
    label: '排行含义',
    detail: '按当前值排序展示 Top 项，可用于识别最突出的压力点或热点对象。',
  },
];

const capacityGuideItems = [
  {
    label: '容量配比',
    detail:
      '已用代表真实消耗，请求代表 Pod 预留的 requests，可分配代表集群当前可分配总量。',
  },
];

const makeRankingTrend = (values: number[]) =>
  values.map((value, index) => ({
    time: now.add(index, 'minute').unix(),
    value1: value,
  }));

const collectionStatusGuideItems = [
  {
    label: '集群健康状态',
    detail: '基于 Elasticsearch 集群整体状态计算，反映分片分配与节点协同是否正常。',
  },
  {
    label: '状态时间线',
    detail: '绿色表示正常，橙色表示警告，红色表示严重。',
  },
];

const metricIconItems = [
  { label: 'Health', color: '#16a34a', icon: <HealthIcon /> },
  { label: 'Memory', color: '#2563eb', icon: <MemoryIcon /> },
  { label: 'Unacked', color: '#f59e0b', icon: <UnackedIcon /> },
  { label: 'Backlog', color: '#8b5cf6', icon: <BacklogIcon /> },
  { label: 'Publish', color: '#ec4899', icon: <PublishIcon /> },
];

const FamilyOverview = () => {
  const [instanceValue, setInstanceValue] = React.useState('mysql-prod-01');
  const [bareInstanceValue, setBareInstanceValue] = React.useState('redis-cache-01');

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Dashboard page header variants
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <DashboardPageHeader
            title="MySQL / db-prod-01"
            displayMode="dashboard"
            onDisplayModeChange={() => undefined}
            timeDefaultValue={{
              selectValue: 15,
              rangePickerVaule: null,
            }}
            onTimeChange={() => undefined}
            onFrequenceChange={() => undefined}
            onRefresh={() => undefined}
            onBack={() => undefined}
            styles={headerStyles}
          />

          <DashboardPageHeader
            title="K8s Cluster / prod-cluster-a"
            displayMode="metrics"
            onDisplayModeChange={() => undefined}
            timeDefaultValue={{
              selectValue: 0,
              rangePickerVaule: [dayjs().subtract(1, 'hour'), dayjs()],
            }}
            onTimeChange={() => undefined}
            onFrequenceChange={() => undefined}
            onRefresh={() => undefined}
            onBack={() => undefined}
            showTimeSelector={false}
            styles={headerStyles}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Instance selector variants
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-[14px] bg-[var(--color-bg-2)] p-4">
            <InstanceSelector
              options={selectorOptions}
              styles={instanceSelectorStyles}
              value={instanceValue}
              onChange={setInstanceValue}
            />
          </div>

          <div className="rounded-[14px] bg-[var(--color-bg-2)] p-4">
            <InstanceSelector
              options={selectorOptions}
              styles={instanceSelectorStyles}
              value="mysql-report-02"
              loading
              onChange={() => undefined}
            />
          </div>

          <div className="rounded-[14px] bg-[var(--color-bg-2)] p-4">
            <InstanceSelector
              options={selectorOptions}
              styles={instanceSelectorStyles}
              value={bareInstanceValue}
              onChange={setBareInstanceValue}
              label=""
              title="Select instance"
              popupWidth={420}
            />
          </div>
        </div>
      </section>

      <DashboardInstanceCard
        styles={instanceStyles}
        instanceName="mysql-prod-01"
        metaItems={['MySQL', '10.0.0.21', 'Production']}
        icon={<DatabaseOutlined />}
        selectorOptions={[
          { label: 'mysql-prod-01', value: 'mysql-prod-01' },
          { label: 'mysql-prod-02', value: 'mysql-prod-02' },
        ]}
        selectorValue="mysql-prod-01"
        onInstanceChange={() => undefined}
      />

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Dashboard panel variants
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <DashboardPanel
            title="连接趋势"
            subtitle="展示最近 1 小时内的连接总量变化"
            guide={dashboardGuideItems}
            styles={dashboardPanelStyles}
          >
            <div className="rounded-[14px] bg-[var(--color-fill-1)] p-6 text-[13px] text-[var(--color-text-2)]">
              Chart canvas or custom panel body goes here.
            </div>
          </DashboardPanel>

          <DashboardPanel
            title="复制延迟"
            styles={dashboardPanelStyles}
          >
            <div className="rounded-[14px] bg-[var(--color-fill-1)] p-6 text-[13px] text-[var(--color-text-2)]">
              A dashboard panel can also render without guide copy or subtitle.
            </div>
          </DashboardPanel>

          <DashboardPanel
            title="线程状态分布"
            subtitle="按状态拆分当前线程数量"
            guide={dashboardGuideItems}
            styles={dashboardPanelStyles}
            bodyClassName="rounded-[14px] bg-[var(--color-fill-1)] p-4"
          >
            <div className="grid grid-cols-2 gap-3 text-[13px] text-[var(--color-text-2)]">
              <div className="rounded-[10px] bg-white/80 p-3">Running</div>
              <div className="rounded-[10px] bg-white/80 p-3">Sleeping</div>
              <div className="rounded-[10px] bg-white/80 p-3">Locked</div>
              <div className="rounded-[10px] bg-white/80 p-3">Waiting</div>
            </div>
          </DashboardPanel>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Guide title variants
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-[14px] bg-[var(--color-bg-2)] p-4">
            <TitleWithGuide
              title="连接使用率"
              items={guideItems}
              styles={guideTooltipStyles}
            />
          </div>

          <div className="rounded-[14px] bg-[var(--color-bg-2)] p-4">
            <TitleWithGuide
              title="运行时长"
              items={[]}
              styles={guideTooltipStyles}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Detail metric row variants
        </div>
        <div className="space-y-3 rounded-[14px] bg-[var(--color-bg-2)] p-4">
          <DetailMetricRow
            label="游标超时数"
            value="182"
            viz="spark"
            trend={trendData}
            color="#2f6bff"
            guide={[
              {
                label: '游标超时数',
                detail: '空闲超时被服务端回收的查询游标累计数，偏高通常说明结果遍历不及时。',
              },
            ]}
            styles={detailMetricRowStyles}
          />
          <DetailMetricRow
            label="CPU 使用率"
            value="72%"
            viz="bar"
            barValue={72}
            tone="warning"
            color="#faad14"
            styles={detailMetricRowStyles}
          />
          <DetailMetricRow
            label="复制状态"
            value="Lagging"
            statusColor="#ff4d4f"
            styles={detailMetricRowStyles}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Collection status card variants
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <CollectionStatusCard
            styles={collectionStatusStyles}
            status={{
              label: '正常',
              detail: '最近一段时间采集稳定，没有出现明显缺口。',
              summary: '采集稳定',
              tagColor: 'success',
            }}
            timeline={[
              'success',
              'success',
              'success',
              'success',
              'success',
              'success',
              'success',
              'empty',
              'success',
              'success',
              'success',
              'success',
            ]}
          />

          <CollectionStatusCard
            styles={collectionStatusStyles}
            status={{
              label: '异常',
              detail: '最近一段时间出现持续采集中断，需要排查节点或网络状态。',
              summary: '连续缺口',
              tagColor: 'error',
            }}
            timeline={[
              'success',
              'success',
              'error',
              'error',
              'error',
              'empty',
              'error',
              'error',
              'success',
              'success',
              'error',
              'error',
            ]}
          />

          <CollectionStatusCard
            styles={collectionStatusStyles}
            status={{
              label: '暂无数据',
              detail: '该实例尚未返回最近时间窗内的指标数据。',
              summary: '等待首次采集',
            }}
            timeline={Array.from({ length: 12 }, () => 'empty' as const)}
          />

          <CollectionStatusCard
            styles={collectionStatusStyles}
            title="集群健康状态"
            status={{
              label: '警告',
              detail: '最近时间窗内存在副本分片未完全分配，但集群仍可处理请求。',
              summary: '副本分片延迟恢复',
              tagColor: 'warning',
            }}
            statusTone="warning"
            guideItems={collectionStatusGuideItems}
            timeline={[
              'success',
              'success',
              'warning',
              'warning',
              'warning',
              'success',
              'success',
              'error',
              'warning',
              'warning',
              'success',
              'success',
            ]}
            legendItems={[
              { key: 'success', label: '正常', color: '#22c55e' },
              { key: 'warning', label: '警告', color: '#f59e0b' },
              { key: 'error', label: '严重', color: '#f04438' },
            ]}
          />

          <CollectionStatusCard
            styles={collectionStatusStyles}
            title="集群健康状态"
            status={{
              label: '未知',
              detail: '当前时间窗内没有返回集群健康样本。',
              summary: '等待健康数据',
            }}
            timeline={[]}
            emptyTimelineText="暂无健康时间线数据"
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Metric icon variants
        </div>
        <div className="rounded-[14px] bg-[var(--color-bg-2)] p-4">
          <div className="grid min-w-[560px] grid-cols-5 gap-4 rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-6">
            {metricIconItems.map((item) => (
              <div
                key={item.label}
                className="flex flex-col items-center gap-3 rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-4 py-5"
              >
                <div style={{ color: item.color }}>{item.icon}</div>
                <span className="text-[13px] font-medium text-[var(--color-text-2)]">
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Dashboard instance card variants
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <DashboardInstanceCard
            instanceName="mysql-report-02"
            metaItems={['MySQL 8.0.36', '10.0.0.22', '报表库']}
            icon={<DatabaseOutlined />}
            selectorOptions={[
              { label: 'db-prod-01', value: 'db-prod-01' },
              { label: 'db-prod-02', value: 'db-prod-02' },
            ]}
            selectorValue="db-prod-02"
            onInstanceChange={() => undefined}
            styles={instanceStyles}
            isDashboardMode={false}
            selectorTitle="Select instance"
          />

          <DashboardInstanceCard
            instanceName="mysql-primary-01"
            metaItems={['MySQL 8.0.36', '10.0.0.21', '主库']}
            icon={<DatabaseOutlined />}
            selectorOptions={[
              { label: 'db-prod-01', value: 'db-prod-01' },
              { label: 'db-prod-02', value: 'db-prod-02' },
            ]}
            selectorValue="db-prod-01"
            onInstanceChange={() => undefined}
            styles={instanceStyles}
            timeSelectorProps={{
              timeDefaultValue: {
                selectValue: 0,
                rangePickerVaule: [dayjs().subtract(2, 'hour'), dayjs()],
              },
              onTimeChange: () => undefined,
              onFrequenceChange: () => undefined,
              onRefresh: () => undefined,
            }}
          />
        </div>
      </section>

    <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">
        Detail panel variants
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <DetailPanel
          title="内存详情"
          subtitle="拆分展示主要内存去向"
          guide={detailGuideItems}
          styles={detailPanelStyles}
        >
          <>
            <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
              <span>RSS</span>
              <strong>1.82 GiB</strong>
            </div>
            <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
              <span>Cache</span>
              <strong>612 MiB</strong>
            </div>
            <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
              <span>Reclaimable</span>
              <strong>148 MiB</strong>
            </div>
          </>
        </DetailPanel>

        <DetailPanel
          title="网络详情"
          subtitle="入口与出口流量拆分"
          styles={detailPanelStyles}
          bodyClassName="bg-[var(--color-bg-1)] ring-1 ring-[var(--color-border-1)]"
        >
          <div className="space-y-2">
            <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
              <span>Ingress</span>
              <strong>38.2 MiB/s</strong>
            </div>
            <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
              <span>Egress</span>
              <strong>27.4 MiB/s</strong>
            </div>
          </div>
        </DetailPanel>
      </div>
    </section>

    <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">
        Detail panel card variants
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <DetailPanelCard
          title="网络与异常"
          subtitle="结果返回与异常信号"
          styles={detailPanelCardStyles}
          guide={[
            {
              label: '网络与异常',
              detail: '用于拆分入出流量与关键异常信号，帮助判断链路和请求质量。',
            },
          ]}
          rows={[
            {
              label: '入流量',
              value: '38.2 MiB/s',
              viz: 'spark',
              trend: trendData,
              color: '#2f6bff',
            },
            {
              label: '出流量',
              value: '27.4 MiB/s',
              viz: 'spark',
              trend: trendData.map((point) => ({
                ...point,
                value1: Number(point.value1) - 6,
              })),
              color: '#27c274',
            },
            {
              label: '复制延迟',
              value: '72%',
              viz: 'bar',
              barValue: 72,
              tone: 'warning',
              color: '#faad14',
            },
            {
              label: '用户断言',
              value: 'Lagging',
              statusColor: '#ff4d4f',
            },
          ]}
        />

        <DetailPanelCard
          title="运行细节"
          subtitle="当前窗口内无可展示样本"
          styles={detailPanelCardStyles}
          rows={[]}
          hasData={false}
        />
      </div>
    </section>

    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_360px]">
      <TrendChartPanel
        title="连接趋势"
        subtitle="展示最近 12 分钟的连接变化"
        styles={trendStyles}
        legends={[
          { label: '当前连接', color: '#2563eb', primary: true },
          { label: '异常连接', color: '#f59e0b' },
        ]}
        data={seriesData}
        metric={metric}
        unit="ms"
        guide={[
          {
            label: '趋势解读',
            detail: '观察主指标与辅指标的同步波动，判断问题是瞬时峰值还是持续升高。',
          },
        ]}
      />

      <RingChartPanel
        title="健康状态分布"
        subtitle="当前对象按状态拆分"
        styles={ringStyles}
        centerValue="42"
        centerCaption="总实例数"
        guide={[
          {
            label: '状态分布',
            detail: '按健康状态拆分当前对象数量，帮助快速判断异常面是否集中。',
          },
        ]}
        data={[
          { name: 'Healthy', value: 28, color: '#16a34a' },
          { name: 'Warning', value: 9, color: '#f59e0b' },
          { name: 'Critical', value: 5, color: '#ef4444' },
        ]}
      />
    </div>

    <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">
        Trend chart panel variants
      </div>
      <div className="space-y-4">
        <TrendChartPanel
          title="QPS 趋势"
          subtitle="带说明块与底部补充信息"
          styles={trendStyles}
          legends={[
            { label: 'Read', color: '#2563eb', primary: true },
            { label: 'Write limit', color: '#94a3b8', dashed: true },
          ]}
          data={seriesData}
          metric={metric}
          unit="counts"
          guide={[
            {
              label: '趋势解读',
              detail: 'Top slot and bottom slot belong to the family contract and keep room for threshold notes or query summaries.',
            },
          ]}
          bodyTop={(
            <div className="mb-3 rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px] text-[var(--color-text-2)]">
              Top slot can host threshold callouts or query notes.
            </div>
          )}
          bodyBottom={(
            <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
              Bottom slot can host annotations or extra summaries.
            </div>
          )}
          seriesStyles={[
            { color: '#2563eb', fillOpacity: 0.08, strokeOpacity: 1, strokeWidth: 2.8 },
            {
              color: '#94a3b8',
              fillOpacity: 0,
              strokeOpacity: 0.9,
              strokeWidth: 2,
              strokeDasharray: '4 4',
            },
          ]}
        />

        <TrendChartPanel
          title="延迟趋势"
          subtitle="支持拖拽选择时间范围"
          styles={trendStyles}
          legends={[{ label: 'P95 latency', color: '#ef4444', primary: true }]}
          data={seriesData}
          metric={metric}
          unit="ms"
          allowSelect
          onXRangeChange={() => undefined}
          guide={[
            {
              label: '趋势解读',
              detail: 'Selection-enabled trend panels stay in the same monitor widget family instead of becoming a separate story root.',
            },
          ]}
        />
      </div>
    </section>

    <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">
        Ring chart panel variants
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <RingChartPanel
          title="缓存命中分布"
          subtitle="热点请求命中比例"
          guide={[
            {
              label: '状态分布',
              detail: 'Custom info rows remain a supported widget-family variant for richer breakdown summaries.',
            },
          ]}
          styles={ringStyles}
          centerValue="87%"
          centerCaption="命中率"
          data={[
            { name: 'Hit', value: 87, color: '#2563eb' },
            { name: 'Miss', value: 13, color: '#94a3b8' },
          ]}
          infoRows={[
            { name: 'Hit', color: '#2563eb', primary: '87.0%', secondary: '(4.2M)' },
            { name: 'Miss', color: '#94a3b8', primary: '13.0%', secondary: '(0.6M)' },
          ]}
          chartExtra={(
            <div className="absolute bottom-3 right-3 rounded-full bg-white/80 px-2 py-1 text-[11px] text-[var(--color-text-3)]">
              Last 1h
            </div>
          )}
        />

        <RingChartPanel
          title="状态分布"
          subtitle="当前暂无可展示的数据"
          styles={ringStyles}
          centerValue="--"
          centerCaption="总实例数"
          data={[]}
          isEmpty
          emptyDescription="No distribution data"
        />
      </div>
    </section>

    <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">
        Ranking and capacity panel variants
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <HorizontalBarPanel
          title="连接使用率 Top"
          subtitle="按当前值展示最高的实例"
          guide={rankingGuideItems}
          styles={horizontalBarStyles}
          items={[
            { label: 'db-prod-01', value: 82, display: '82%', color: '#2563eb', max: 100 },
            { label: 'db-prod-02', value: 68, display: '68%', color: '#14b8a6', max: 100 },
            { label: 'db-report-01', value: 54, display: '54%', color: '#f59e0b', max: 100 },
          ]}
        />

        <HorizontalBarPanel
          title="节点网络趋势"
          subtitle="展示近 10 分钟的吞吐波动"
          guide={rankingGuideItems}
          styles={horizontalBarStyles}
          items={[
            {
              label: 'node-a',
              value: 0,
              display: '182 MiB/s',
              color: '#2563eb',
              max: 1,
              trend: makeRankingTrend([110, 124, 132, 141, 154, 149, 160, 171, 176, 182]),
            },
            {
              label: 'node-b',
              value: 0,
              display: '146 MiB/s',
              color: '#14b8a6',
              max: 1,
              trend: makeRankingTrend([88, 92, 101, 111, 118, 126, 131, 137, 141, 146]),
            },
          ]}
        />

        <HorizontalBarPanel
          title="Pod CPU 排行"
          subtitle="按当前 CPU 使用量从高到低排序"
          guide={rankingGuideItems}
          styles={horizontalBarStyles}
          tiered
          items={[
            { label: 'payments/api-7f6c9', value: 910, display: '910m', color: '#ef4444', max: 1000, rank: 1 },
            { label: 'checkout/worker-5d4aa', value: 740, display: '740m', color: '#f59e0b', max: 1000, rank: 2 },
            { label: 'search/indexer-66fb2', value: 620, display: '620m', color: '#2563eb', max: 1000, rank: 3 },
            { label: 'report/scheduler-21aaf', value: 410, display: '410m', color: '#14b8a6', max: 1000, rank: 4 },
          ]}
        />

        <StackedBarPanel
          title="容量配比"
          subtitle="已用 / 已请求 / 可分配"
          guide={capacityGuideItems}
          styles={stackedBarStyles}
          rows={[
            {
              label: 'CPU',
              used: 44,
              requested: 71,
              total: 96,
              usedDisplay: '44 Core',
              requestedDisplay: '71 Core',
              totalDisplay: '96 Core',
            },
            {
              label: 'Memory',
              used: 228,
              requested: 312,
              total: 512,
              usedDisplay: '228 GiB',
              requestedDisplay: '312 GiB',
              totalDisplay: '512 GiB',
            },
          ]}
        />

        <StackedBarPanel
          title="容量配比"
          subtitle="请求已超过可分配容量"
          guide={capacityGuideItems}
          styles={stackedBarStyles}
          rows={[
            {
              label: 'CPU',
              used: 61,
              requested: 118,
              total: 96,
              usedDisplay: '61 Core',
              requestedDisplay: '118 Core',
              totalDisplay: '96 Core',
            },
            {
              label: 'Memory',
              used: 340,
              requested: 612,
              total: 512,
              usedDisplay: '340 GiB',
              requestedDisplay: '612 GiB',
              totalDisplay: '512 GiB',
            },
          ]}
        />
      </div>
    </section>

    <div className="grid gap-6 lg:grid-cols-3">
      <StatCard
        title="平均响应时间"
        value="482"
        unit="ms"
        color="#1677ff"
        icon={<DatabaseOutlined />}
        iconStyle={{ color: '#1677ff' }}
        trendData={trendData}
        styles={statStyles}
        compare={{ direction: 'down', value: '12.4%' }}
        compareFavorableDirection="down"
        footer="近 15 分钟 · P95"
      />
      <StatCard
        title="可用性"
        value="99.21"
        unit="%"
        color="#13c2c2"
        icon={<ClockCircleOutlined />}
        iconStyle={{ color: '#13c2c2' }}
        trendData={trendData}
        styles={statStyles}
        compare={{ direction: 'down', value: '0.42%' }}
        compareFavorableDirection="up"
        footer="近 24 小时 · SLA"
        extra={(
          <div className="rounded-[12px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2 text-[13px] text-[var(--color-text-2)]">
            受计划内维护窗口影响
          </div>
        )}
      />
      <StatCard
        title="在线时长"
        value="18.2"
        unit="hour"
        color="#52c41a"
        icon={<CheckCircleOutlined />}
        iconStyle={{ color: '#52c41a' }}
        hideTrend
        styles={statStyles}
        compare={null}
        footer={(
          <>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-[#52c41a]" />
              正常采集
            </span>
            <span>最近重启: 2 小时前</span>
          </>
        )}
      />
      <StatCard
        title="写入吞吐"
        value="--"
        unit=""
        color="#722ed1"
        icon={<DatabaseOutlined />}
        iconStyle={{ color: '#722ed1' }}
        trendData={[]}
        styles={statStyles}
        noDataType="error"
        compare={{ direction: 'flat', value: '暂无数据' }}
        footer="采集异常 · 最近 15 分钟"
      />
    </div>
    </div>
  );
};

const meta = {
  title: 'Business/Monitor/Widgets/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1180, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
