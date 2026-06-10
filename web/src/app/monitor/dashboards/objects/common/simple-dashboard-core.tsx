'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChartData, Dimension, MetricItem, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import {
  normalizeDisplayText,
  parseLegacyParamList,
  buildInstanceDisplayName,
  buildInstanceSearchTokens,
  formatEnumValue,
  formatMetricValue,
  buildSearchParams,
  getLatestChartValue,
  mergeChartSeries,
  buildPreviousPeriodTimeValues,
  getPeriodCompare,
  runWithConcurrency,
  toMetricSeries,
  buildMetricItem,
  getCollectionStatus,
  buildCollectionStatusTimeline
} from '../../shared/utils';
import {
  CompareFavorableDirection,
  GuideItem,
  MetricEnumMap,
  MetricUnit,
  TrendLegendItem
} from '../../shared/types';

export type SimpleMetricUnit = MetricUnit;

export interface SimpleMetricConfig {
  name: string;
  display_name: string;
  description: string;
  unit: SimpleMetricUnit;
  query: string;
  color: string;
  dimensions?: Dimension[];
}

export interface MetricSeries extends SimpleMetricConfig {
  viewData: ChartData[];
  loadState: 'success' | 'error';
}

interface InstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
}

export interface SummaryFieldConfig {
  label: string;
  metric: string;
  unit?: SimpleMetricUnit;
  formatter?: 'duration' | 'enumHealth' | 'startedAt';
  enumMap?: MetricEnumMap;
  /** 详情行语义色：error→红 / warning→琥珀 / 缺省→中性蓝。仅影响缩略图与数值配色。 */
  tone?: 'error' | 'warning' | 'normal';
}

export interface SummaryCardConfig {
  title: string;
  guide: GuideItem[];
  metric: string;
  unit?: SimpleMetricUnit;
  color: string;
  icon: 'api' | 'clock' | 'database' | 'node' | 'thunder' | 'health' | 'memory' | 'unacked' | 'backlog' | 'publish';
  compare?: boolean;
  compareFavorableDirection?: CompareFavorableDirection;
  footer?: SummaryFieldConfig[];
  hideTrend?: boolean;
  formatter?: 'duration' | 'enumHealth' | 'startedAt';
  enumMap?: MetricEnumMap;
  /** 标记为运行时长卡片，启用 relaxed 布局 + 运行状态指示器 */
  isUptimeCard?: boolean;
}

export interface ChartConfig {
  title: string;
  subtitle: string;
  guide: GuideItem[];
  metric: string;
  series: Array<{
    metric: string;
    label: string;
    color: string;
    unit?: SimpleMetricUnit;
    /** 'limit' renders a dashed, dimmed ceiling line (e.g. mem_limit). Defaults to solid. */
    style?: 'solid' | 'limit';
  }>;
}

export interface DetailPanelConfig {
  title: string;
  subtitle: string;
  rows: SummaryFieldConfig[];
}

export interface RingSegmentConfig {
  label: string;
  metric: string;
  color: string;
  unit?: SimpleMetricUnit;
  transform?: 'percentRemaining';
}

export interface RingPanelConfig {
  title: string;
  subtitle: string;
  guide: GuideItem[];
  centerMetric: string;
  centerCaption: string;
  centerUnit?: SimpleMetricUnit;
  centerFormatter?: 'duration';
  segments: RingSegmentConfig[];
}

export interface BarPanelConfig {
  title: string;
  subtitle: string;
  guide: GuideItem[];
  items: Array<{ label: string; metric: string; color: string; unit?: SimpleMetricUnit }>;
  /** true 时每行渲染 sparkline 趋势(速率/计数类);缺省保留进度条(分布/对比类)。 */
  showTrend?: boolean;
}

/** A binary/flag signal shown as a status row (dot + state badge) rather than a value bar.
 *  By default any non-zero value is treated as "firing" (alarm tone); an enumMap supplies
 *  state labels. Set `invertTone` for "1 = healthy" flags (e.g. Consul passing), where a
 *  positive value is the OK state and zero is the alarm state. */
export interface StatusItemConfig {
  label: string;
  metric: string;
  enumMap?: MetricEnumMap;
  invertTone?: boolean;
}

export interface StatusPanelConfig {
  title: string;
  subtitle: string;
  guide: GuideItem[];
  items: StatusItemConfig[];
}

export interface SimpleDashboardConfig {
  routeKey: string;
  pageTitle: string;
  objectFallbackName: string;
  instanceType: string;
  collectionStatusQuery: string;
  metrics: SimpleMetricConfig[];
  metaItems?: string[];
  /**
   * 标题头(对象名后)动态展示的指标 chip(如版本)。通用能力:每个对象按需声明,
   * 指标有数据则显示「label: 值」,无数据自动跳过。适合版本/构建号等静态身份信息。
   */
  metaMetrics?: Array<{ label: string; metric: string; unit?: SimpleMetricUnit }>;
  summaryCards: SummaryCardConfig[];
  charts: ChartConfig[];
  ringPanels?: RingPanelConfig[];
  barPanels?: BarPanelConfig[];
  statusPanels?: StatusPanelConfig[];
  details: DetailPanelConfig[];
}

export interface PreparedSummaryCard {
  card: SummaryCardConfig;
  mainValue: { value: string; unit: string };
  valueColor?: string;
  compare: ReturnType<typeof getPeriodCompare> | null;
  footerItems: Array<{ label: string; value: string }>;
  trendData: ChartData[];
  noDataType: 'empty' | 'error';
  /** 运行时长卡片的重启状态，仅 isUptimeCard=true 时有值 */
  uptimeState?: { label: string; tone: 'success' | 'warning' | 'empty' };
}

export interface PreparedChartPanel {
  chart: ChartConfig;
  data: ChartData[];
  metric: MetricItem;
  unit: SimpleMetricUnit;
  legends: TrendLegendItem[];
  seriesStyles: Array<{
    color: string;
    unit?: SimpleMetricUnit;
    fillOpacity?: number;
    strokeOpacity?: number;
    strokeWidth?: number;
    strokeDasharray?: string;
  }>;
}

export interface PreparedRingPanel {
  panel: RingPanelConfig;
  data: Array<{ name: string; value: number; color: string; display: string }>;
  centerValue: string;
  isEmpty: boolean;
}

export interface PreparedBarPanel {
  panel: BarPanelConfig;
  items: Array<{ label: string; value: number; display: string; color: string; max: number; trend?: ChartData[] }>;
}

export interface PreparedStatusPanel {
  panel: StatusPanelConfig;
  items: Array<{ label: string; state: string; tone: 'ok' | 'alarm' | 'unknown' }>;
}

export type DetailRowViz = 'bar' | 'spark' | 'none';

export interface PreparedDetailRow {
  label: string;
  value: string;
  /** bar=百分比进度条；spark=速率/计数迷你趋势；none=纯数值(状态/枚举/时长/无时序) */
  viz: DetailRowViz;
  /** spark 用:完整时序 */
  trend: ChartData[];
  /** bar 用:当前值 clamp 到 0–100 */
  barValue: number;
  tone: 'error' | 'warning' | 'normal';
  /** 枚举/状态行:枚举项自带的语义色(undefined=非枚举或无匹配) */
  statusColor?: string;
  /** sparkline 语义色:取该指标 config.color,与 KPI 卡 / 趋势图 / 异常信号条同源,统一缩略图配色 */
  color?: string;
}

export interface PreparedDetailPanel {
  panel: DetailPanelConfig;
  rows: PreparedDetailRow[];
  hasData: boolean;
}

const METRIC_QUERY_CONCURRENCY = 4;

export const countRestartsInRange = (data: ChartData[] = []): number => {
  const points = data
    .map((point) => ({ time: Number(point.time), value: Number(point.value1 ?? 0) }))
    .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value) && p.value >= 0)
    .sort((a, b) => a.time - b.time);

  if (points.length < 2) return 0;

  let restartCount = 0;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const drop = prev.value - curr.value;
    const gapSeconds = Math.max((curr.time - prev.time) / 1000, 0);
    const tolerance = Math.max(30, gapSeconds * 0.2);
    if (drop > tolerance && curr.value < prev.value * 0.98) restartCount++;
  }
  return restartCount;
};

export const formatDuration = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0s';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
};

const CLUSTER_HEALTH_COLORS = {
  normal: '#27c274',
  warning: '#ff8a1f',
  critical: '#ff4d4f',
  unknown: '#94a3b8'
} as const;

const formatClusterHealth = (value: number) => {
  if (!Number.isFinite(value)) return { value: '--', unit: '', color: CLUSTER_HEALTH_COLORS.unknown };
  if (value <= 1) return { value: '正常', unit: '', color: CLUSTER_HEALTH_COLORS.normal };
  if (value <= 2) return { value: '警告', unit: '', color: CLUSTER_HEALTH_COLORS.warning };
  return { value: '严重', unit: '', color: CLUSTER_HEALTH_COLORS.critical };
};

const formatMappedEnum = (value: number, enumMap?: MetricEnumMap) => {
  const formatted = formatEnumValue(value, enumMap);
  return { value: formatted.value, unit: '', color: formatted.color };
};

export function useSimpleDashboardData(config: SimpleDashboardConfig) {
  const viewApi = useViewApi();
  const monitorApi = useMonitorApi();
  const router = useRouter();

  // Stabilize API functions — useViewApi/useMonitorApi return new objects every render,
  // so we must ref-stabilize them to prevent useCallback deps from constantly changing.
  const getInstanceQueryRef = useRef(viewApi.getInstanceQuery);
  const getInstanceListRef = useRef(monitorApi.getInstanceList);
  useEffect(() => { getInstanceQueryRef.current = viewApi.getInstanceQuery; });
  useEffect(() => { getInstanceListRef.current = monitorApi.getInstanceList; });

  const getInstanceQuery = useCallback(
    (...args: Parameters<typeof viewApi.getInstanceQuery>) => getInstanceQueryRef.current(...args),
    []
  );
  const getInstanceList = useCallback(
    (...args: Parameters<typeof monitorApi.getInstanceList>) => getInstanceListRef.current(...args),
    []
  );
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const [loading, setLoading] = useState(true);
  const [displayMode, setDisplayMode] = useState<'dashboard' | 'metrics'>('dashboard');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({ timeRange: [], originValue: 15 });
  const [timeDefaultValue, setTimeDefaultValue] = useState<TimeSelectorDefaultValue>({ selectValue: 15, rangePickerVaule: null });
  const [frequence, setFrequence] = useState<number>(0);
  const [series, setSeries] = useState<Record<string, MetricSeries>>({});
  const [previousSeries, setPreviousSeries] = useState<Record<string, MetricSeries>>({});
  const [collectionStatusMetric, setCollectionStatusMetric] = useState<MetricSeries | null>(null);
  const [instanceOptions, setInstanceOptions] = useState<InstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);
  const loadSeqRef = useRef(0);

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || config.objectFallbackName;
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || config.objectFallbackName;
  const rawInstanceId = searchParams.get('instance_id') || '';
  const rawInstanceIdValues = searchParams.get('instance_id_values') || '';
  const rawInstanceIdKeys = searchParams.get('instance_id_keys') || 'instance_id';
  const instanceName = searchParams.get('instance_name') || '--';

  // Stable memoized values - avoids new array references on every render
  const parsedLegacyInstanceIds = useMemo(() => parseLegacyParamList(rawInstanceId), [rawInstanceId]);
  const instanceId: React.Key = parsedLegacyInstanceIds[0] || rawInstanceId || '';
  const idValues = useMemo(() => {
    const explicitValues = parseLegacyParamList(rawInstanceIdValues);
    if (explicitValues.length > 0) return explicitValues;
    if (parsedLegacyInstanceIds.length > 0) return parsedLegacyInstanceIds;
    const normalizedInstanceId = normalizeDisplayText(rawInstanceId);
    return normalizedInstanceId ? [normalizedInstanceId] : [];
  }, [rawInstanceIdValues, parsedLegacyInstanceIds, rawInstanceId]);
  const instanceIdKeys = useMemo(
    () => rawInstanceIdKeys.split(',').filter(Boolean),
    [rawInstanceIdKeys]
  );
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || config.objectFallbackName;
  const normalizedInstanceName = normalizeDisplayText(instanceName);
  const isDashboardMode = displayMode === 'dashboard';

  useEffect(() => {
    if (!monitorObjectId) {
      setInstanceOptions([]);
      return;
    }
    let active = true;
    const loadInstances = async () => {
      try {
        setInstanceLoading(true);
        const data = await getInstanceList(monitorObjectId, { page_size: -1 });
        if (!active) return;
        const uniqueOptions = new Map<string, InstanceOption>();
        (data?.results || []).forEach((item: any) => {
          const value = String(item.instance_id || '');
          if (!value || uniqueOptions.has(value)) return;
          const label = buildInstanceDisplayName(item);
          uniqueOptions.set(value, {
            label,
            value,
            instanceIdValues: Array.isArray(item.instance_id_values) && item.instance_id_values.length ? item.instance_id_values : [value],
            searchTokens: buildInstanceSearchTokens(item, label)
          });
        });
        setInstanceOptions(Array.from(uniqueOptions.values()));
      } catch {
        if (active) setInstanceOptions([]);
      } finally {
        if (active) setInstanceLoading(false);
      }
    };
    loadInstances();
    return () => {
      active = false;
    };
  }, [getInstanceList, monitorObjectId]);

  const idValuesKey = useMemo(() => JSON.stringify(idValues), [idValues]);
  const currentInstanceCandidates = useMemo(
    () => instanceOptions.filter(
      (item) => item.value === String(instanceId || '') || item.instanceIdValues.some((value) => idValues.includes(value))
    ),
    [instanceOptions, instanceId, idValues]
  );
  const currentInstanceOption = useMemo(
    () =>
      currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) ||
      currentInstanceCandidates[0],
    [currentInstanceCandidates, normalizedInstanceName]
  );
  const resolvedInstanceName = useMemo(
    () => currentInstanceOption?.label || normalizedInstanceName || '--',
    [currentInstanceOption, normalizedInstanceName]
  );
  const hasReadableInstanceName = Boolean(normalizedInstanceName && normalizedInstanceName !== String(instanceId || ''));
  const instanceSelectOptions = useMemo(() => {
    const options = [...instanceOptions];
    const selectedValue = String(instanceId || '');
    if (selectedValue && hasReadableInstanceName && !options.some((item) => item.value === selectedValue)) {
      options.unshift({
        value: selectedValue,
        label: normalizedInstanceName,
        instanceIdValues: idValues.length ? idValues : [selectedValue],
        searchTokens: [normalizedInstanceName]
      });
    }
    return options;
  }, [hasReadableInstanceName, idValues, instanceId, instanceOptions, normalizedInstanceName]);
  const instanceSelectValue = currentInstanceOption?.value || (hasReadableInstanceName && instanceId ? String(instanceId) : undefined);

  // Metrics that StatCards directly depend on — loaded first so KPI cards fill in quickly.
  const summaryMetricNames = useMemo(
    () => new Set(config.summaryCards.map((c) => c.metric)),
    [config.summaryCards]
  );

  const loadSingleMetric = useCallback(
    (metric: SimpleMetricConfig, tv: TimeValuesProps) =>
      getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, tv, undefined, false))
        .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
        .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const),
    [getInstanceQuery, idValues, instanceId, instanceIdKeys, resolvedInstanceName]
  );

  const loadMetrics = useCallback(async (silent = false) => {
    const loadSeq = loadSeqRef.current + 1;
    loadSeqRef.current = loadSeq;

    if (!silent) setLoading(true);
    try {
      if (displayMode === 'dashboard') {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = config.metrics.filter((m) => config.summaryCards.some((c) => c.compare && c.metric === m.name));

        // ── Group 1: summary metrics (StatCard values) ──
        const summaryMetrics = config.metrics.filter((m) => summaryMetricNames.has(m.name));
        const trendMetrics = config.metrics.filter((m) => !summaryMetricNames.has(m.name));

        const summaryResultsPromise = runWithConcurrency(
          summaryMetrics,
          METRIC_QUERY_CONCURRENCY,
          (metric) => loadSingleMetric(metric, timeValues)
        );
        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(
          buildSearchParams(config.collectionStatusQuery, 'counts', idValues, instanceIdKeys, timeValues, undefined, false)
        )
          .then((result) =>
            toMetricSeries(
              {
                name: `${config.routeKey}_collection_status`,
                display_name: '采集状态',
                description: `${config.objectFallbackName} 监控探针采集状态。`,
                unit: 'counts',
                query: config.collectionStatusQuery,
                color: '#27c274'
              },
              result,
              instanceId,
              resolvedInstanceName,
              idValues,
              instanceIdKeys
            )
          )
          .catch(
            () =>
              ({
                name: `${config.routeKey}_collection_status`,
                display_name: '采集状态',
                description: `${config.objectFallbackName} 监控探针采集状态。`,
                unit: 'counts',
                query: config.collectionStatusQuery,
                color: '#27c274',
                viewData: [],
                loadState: 'error' as const
              }) satisfies MetricSeries
          );
        const previousMetricResultsPromise = previousTimeValues
          ? runWithConcurrency(
            compareMetrics,
            METRIC_QUERY_CONCURRENCY,
            (metric) => loadSingleMetric(metric, previousTimeValues)
          )
          : Promise.resolve([] as Array<readonly [string, MetricSeries]>);

        if (!silent) {
          setPreviousSeries({});
        }

        previousMetricResultsPromise.then((previousResults) => {
          if (loadSeqRef.current !== loadSeq) return;
          setPreviousSeries(Object.fromEntries(previousResults));
        });

        // KPI cards and collection status should render as soon as their data is ready.
        const [summaryResults, collectionStatus] = await Promise.all([
          summaryResultsPromise,
          collectionStatusPromise
        ]);

        if (loadSeqRef.current !== loadSeq) return;

        setSeries((prev) => (silent ? { ...prev, ...Object.fromEntries(summaryResults) } : Object.fromEntries(summaryResults)));
        setCollectionStatusMetric(collectionStatus);
        if (!silent) setLoading(false);

        // ── Group 2: trend/chart metrics — loaded async in background ──
        if (trendMetrics.length > 0) {
          runWithConcurrency(trendMetrics, METRIC_QUERY_CONCURRENCY, (metric) => loadSingleMetric(metric, timeValues))
            .then((trendResults) => {
              if (loadSeqRef.current !== loadSeq) return;
              setSeries((prev) => ({ ...prev, ...Object.fromEntries(trendResults) }));
            });
        }
      } else {
        setSeries({});
        setPreviousSeries({});
        setCollectionStatusMetric(null);
        if (!silent) setLoading(false);
      }
    } catch {
      if (loadSeqRef.current === loadSeq && !silent) setLoading(false);
    }
  }, [config, displayMode, getInstanceQuery, idValues, idValuesKey, instanceId, instanceIdKeys, loadSingleMetric, resolvedInstanceName, summaryMetricNames, timeValues]);

  useEffect(() => {
    if (displayMode === 'dashboard') {
      loadMetrics();
      return;
    }
    setLoading(false);
    // loadMetrics already captures displayMode, idValuesKey, instanceId, timeValues internally.
    // Do NOT add timeValues here to avoid double-trigger infinite loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadMetrics]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (frequence > 0 && displayMode === 'dashboard') {
      timerRef.current = setInterval(() => loadMetrics(true), frequence);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [displayMode, frequence, loadMetrics]);

  const metricMap = useMemo(() => series, [series]);
  const previousMetricMap = useMemo(() => previousSeries, [previousSeries]);

  const getLatest = useCallback((name: string) => getLatestChartValue(metricMap[name]?.viewData || []), [metricMap]);
  const hasMetricData = useCallback((name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  }, [metricMap]);
  const getNoDataType = useCallback((...metricNames: string[]): 'empty' | 'error' => {
    const targets = metricNames.map((name) => metricMap[name]).filter(Boolean);
    return targets.length > 0 && targets.every((metric) => metric?.loadState === 'error') ? 'error' : 'empty';
  }, [metricMap]);
  const formatField = useCallback((field: SummaryFieldConfig) => {
    const value = getLatest(field.metric);
    if (!hasMetricData(field.metric)) return '--';
    if (field.formatter === 'duration') return formatDuration(value);
    if (field.formatter === 'enumHealth') return formatClusterHealth(value).value;
    if (field.enumMap) return formatMappedEnum(value, field.enumMap).value;
    if (field.formatter === 'startedAt') {
      if (!Number.isFinite(value) || value < 0) return '--';
      return dayjs().subtract(Math.floor(value), 'second').format('YYYY-MM-DD HH:mm:ss');
    }
    const formatted = formatMetricValue(value, field.unit || metricMap[field.metric]?.unit || 'none');
    return `${formatted.value}${formatted.unit}`;
  }, [getLatest, hasMetricData, metricMap]);
  const getTransformedValue = useCallback((metric: string, transform?: RingSegmentConfig['transform']) => {
    const value = getLatest(metric);
    if (!hasMetricData(metric)) return 0;
    if (transform === 'percentRemaining') return Math.max(100 - value, 0);
    return Math.max(value, 0);
  }, [getLatest, hasMetricData]);
  const formatTransformedValue = useCallback((metric: string, unit?: SimpleMetricUnit, transform?: RingSegmentConfig['transform']) => {
    if (!hasMetricData(metric)) return '--';
    const metricUnit = unit || metricMap[metric]?.unit || 'none';
    const formatted = formatMetricValue(getTransformedValue(metric, transform), metricUnit);
    return `${formatted.value}${formatted.unit}`;
  }, [getTransformedValue, hasMetricData, metricMap]);

  const summaryCards = useMemo<PreparedSummaryCard[]>(() => (
    config.summaryCards.map((card) => {
      const healthResult = card.formatter === 'enumHealth' && hasMetricData(card.metric)
        ? formatClusterHealth(getLatest(card.metric))
        : null;
      const enumResult = card.enumMap && hasMetricData(card.metric)
        ? formatMappedEnum(getLatest(card.metric), card.enumMap)
        : null;

      const mainValue = !hasMetricData(card.metric)
        ? { value: '--', unit: '' }
        : card.formatter === 'duration'
          ? { value: formatDuration(getLatest(card.metric)), unit: '' }
          : healthResult
            ? { value: healthResult.value, unit: healthResult.unit }
            : enumResult
              ? { value: enumResult.value, unit: enumResult.unit }
              : formatMetricValue(getLatest(card.metric), card.unit || metricMap[card.metric]?.unit || 'none');

      const uptimeState = card.isUptimeCard
        ? !hasMetricData(card.metric)
          ? { label: '状态未知', tone: 'empty' as const }
          : countRestartsInRange(metricMap[card.metric]?.viewData || []) > 0
            ? { label: '期间有重启', tone: 'warning' as const }
            : { label: '运行正常', tone: 'success' as const }
        : undefined;

      return {
        card,
        mainValue,
        valueColor: enumResult?.color || healthResult?.color,
        compare: card.compare
          ? getPeriodCompare(getLatest(card.metric), getLatestChartValue(previousMetricMap[card.metric]?.viewData || []))
          : null,
        footerItems: (card.footer || []).map((field) => ({ label: field.label, value: formatField(field) })),
        trendData: metricMap[card.metric]?.viewData || [],
        noDataType: getNoDataType(card.metric),
        uptimeState
      };
    })
  ), [config.summaryCards, formatField, getLatest, getNoDataType, hasMetricData, metricMap, previousMetricMap]);

  const chartPanels = useMemo<PreparedChartPanel[]>(() => (
    config.charts.map((chart) => ({
      chart,
      data: mergeChartSeries(chart.series.map((item) => ({ key: item.metric, label: item.label, data: metricMap[item.metric]?.viewData || [] }))),
      metric: buildMetricItem(metricMap[chart.metric] || config.metrics.find((metric) => metric.name === chart.metric) || config.metrics[0]),
      unit: metricMap[chart.metric]?.unit || config.metrics.find((metric) => metric.name === chart.metric)?.unit || 'none',
      legends: chart.series.map((item, index) => ({ label: item.label, color: item.color, primary: index === 0 })),
      seriesStyles: chart.series.map((item, index) => {
        const isLimit = item.style === 'limit';
        return {
          color: item.color,
          unit: item.unit || metricMap[item.metric]?.unit,
          fillOpacity: isLimit ? 0 : index === 0 ? 0.08 : 0.03,
          strokeOpacity: isLimit ? 0.55 : index === 0 ? 1 : 0.72,
          strokeWidth: isLimit ? 1.6 : index === 0 ? 2.8 : 2.2,
          strokeDasharray: isLimit ? '6 4' : undefined
        };
      })
    }))
  ), [config.charts, config.metrics, metricMap]);

  const ringPanels = useMemo<PreparedRingPanel[]>(() => (
    (config.ringPanels || []).map((panel) => ({
      panel,
      data: panel.segments.map((item) => ({
        name: item.label,
        value: getTransformedValue(item.metric, item.transform),
        color: item.color,
        display: formatTransformedValue(item.metric, item.unit, item.transform)
      })),
      centerValue: hasMetricData(panel.centerMetric)
        ? panel.centerFormatter === 'duration'
          ? formatDuration(getLatest(panel.centerMetric))
          : formatTransformedValue(panel.centerMetric, panel.centerUnit)
        : '--',
      isEmpty: !hasMetricData(panel.centerMetric) && panel.segments.every((item) => !hasMetricData(item.metric))
    }))
  ), [config.ringPanels, formatTransformedValue, getLatest, getTransformedValue, hasMetricData]);

  const barPanels = useMemo<PreparedBarPanel[]>(() => (
    (config.barPanels || []).map((panel) => {
      const items = panel.items.map((item) => {
        const value = hasMetricData(item.metric) ? Math.max(getLatest(item.metric), 0) : 0;
        const formatted = hasMetricData(item.metric)
          ? formatMetricValue(value, item.unit || metricMap[item.metric]?.unit || 'none')
          : { value: '--', unit: '' };
        return {
          label: item.label,
          value,
          display: `${formatted.value}${formatted.unit}`,
          color: item.color,
          max: 1,
          // 速率/计数类面板(showTrend)透传时序 → 渲染 sparkline;分布类不传 → 保留进度条。
          trend: panel.showTrend ? (metricMap[item.metric]?.viewData ?? []) : undefined
        };
      });
      const max = Math.max(...items.map((item) => item.value), 1);
      return { panel, items: items.map((item) => ({ ...item, max })) };
    })
  ), [config.barPanels, getLatest, hasMetricData, metricMap]);

  const statusPanels = useMemo<PreparedStatusPanel[]>(() => (
    (config.statusPanels || []).map((panel) => ({
      panel,
      items: panel.items.map((item) => {
        if (!hasMetricData(item.metric)) {
          return { label: item.label, state: '--', tone: 'unknown' as const };
        }
        const value = Math.round(getLatest(item.metric));
        const isOk = item.invertTone ? value > 0 : value <= 0;
        const tone = isOk ? ('ok' as const) : ('alarm' as const);
        const mapped = item.enumMap?.[value];
        // Map known enum states directly; otherwise fall back to tone-based wording so
        // a non-boolean reading (e.g. 835) still reads as "告警" rather than a raw number.
        const state = mapped ? mapped.label : tone === 'ok' ? '正常' : '告警';
        return { label: item.label, state, tone };
      })
    }))
  ), [config.statusPanels, getLatest, hasMetricData]);

  const detailPanels = useMemo<PreparedDetailPanel[]>(() => (
    config.details.map((panel) => {
      const rows: PreparedDetailRow[] = panel.rows
        .map((row) => {
          const value = formatField(row);
          // 状态/枚举/时长类不画图(趋势无意义),只展示文本。
          const isTextual = Boolean(row.formatter || row.enumMap);
          // 仅真实可度量的数值型指标才画图;unit 缺省或 'none'(标识符编码/版本号等)一律纯文本。
          const isChartableUnit = Boolean(row.unit) && row.unit !== 'none';
          const series = metricMap[row.metric]?.viewData ?? [];
          const hasSeries = series.length > 0;
          let viz: DetailRowViz = 'none';
          if (value !== '--' && !isTextual && isChartableUnit && hasSeries) {
            // 实时数值统一用 sparkline 呈现趋势(含百分比——趋势比静态"满度"更有意义)。
            viz = 'spark';
          }
          const latest = getLatest(row.metric);
          // 枚举/状态行:取枚举项自带语义色(与 KPI 卡 valueColor 口径一致);无 enumMap/无数据/无匹配则 undefined。
          const statusColor = row.enumMap && hasMetricData(row.metric) ? formatMappedEnum(latest, row.enumMap).color : undefined;
          // sparkline 语义色:取该指标 config.color,使详情行缩略图与 KPI/趋势/异常信号条配色一致。
          const color = config.metrics.find((m) => m.name === row.metric)?.color;
          return {
            label: row.label,
            value,
            viz,
            trend: series,
            barValue: Number.isFinite(latest) ? Math.max(0, Math.min(100, latest)) : 0,
            tone: row.tone ?? 'normal',
            statusColor,
            color
          };
        })
        .filter((row) => row.value !== '--');

      return {
        panel,
        rows,
        hasData: rows.length > 0
      };
    })
  ), [config.details, formatField, metricMap, getLatest, hasMetricData]);

  const collectionStatus = getCollectionStatus(collectionStatusMetric, config.objectFallbackName);
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric?.loadState, collectionStatusMetric?.viewData);
  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : config.pageTitle;
  // 标题头 meta-metric chips:有数据则「label: 值」放对象名后,无数据自动跳过(通用能力)。
  const metaMetricChips = (config.metaMetrics || [])
    .filter((m) => hasMetricData(m.metric))
    .map((m) => `${m.label}: ${formatField({ label: m.label, metric: m.metric, unit: m.unit })}`);
  const objectMetaItems = [objectDisplayText, ...metaMetricChips, ...(config.metaItems || []), '时区: Asia/Shanghai'];

  const onTimeChange = (val: number[], originValue: number | null) => setTimeValues({ timeRange: val, originValue });
  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    if (!arr?.[0] || !arr?.[1]) return;
    const start = arr[0].valueOf();
    const end = arr[1].valueOf();
    if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) return;
    setTimeDefaultValue((prev) => ({ ...prev, rangePickerVaule: arr, selectValue: 0 }));
    setTimeValues({ timeRange: [start, end], originValue: 0 });
  };
  const goBack = () => router.push('/monitor/view');
  const onInstanceChange = (value: string) => {
    const target = instanceOptions.find((item) => item.value === value);
    const params = new URLSearchParams(searchParams.toString());
    params.set('instance_id', value);
    params.set('instance_name', String(target?.label || normalizedInstanceName || resolvedInstanceName || ''));
    params.set('instance_id_values', (target?.instanceIdValues || [value]).join(','));
    router.push(`/monitor/view/dashboard/${config.routeKey}?${params.toString()}`);
  };
  const onRefresh = () => {
    if (displayMode === 'dashboard') {
      loadMetrics();
    } else {
      setMetricsRefreshSignal((value) => value + 1);
    }
  };

  return {
    loading,
    displayMode,
    setDisplayMode,
    pageTitle,
    timeValues,
    timeDefaultValue,
    frequence,
    setFrequence,
    metricsRefreshSignal,
    monitorObjectId,
    monitorObjectName,
    instanceId,
    resolvedInstanceName,
    idValues,
    collectionStatus,
    collectionStatusTimeline,
    objectMetaItems,
    objectFallbackName: config.objectFallbackName,
    instanceSelectValue,
    instanceLoading,
    instanceSelectOptions,
    currentInstanceLabel: currentInstanceOption?.label || normalizedInstanceName || resolvedInstanceName,
    isDashboardMode,
    summaryCards,
    chartPanels,
    ringPanels,
    barPanels,
    statusPanels,
    detailPanels,
    onTimeChange,
    onRefresh,
    onXRangeChange,
    onBack: goBack,
    onInstanceChange
  };
}
