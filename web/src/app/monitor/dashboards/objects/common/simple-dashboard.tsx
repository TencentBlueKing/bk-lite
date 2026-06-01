'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ApiOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  NodeIndexOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import EChartsLineChart from '../../shared/widgets/echarts-line-chart';
import MetricViews from '@/app/monitor/components/metric-views';
import useMonitorApi from '@/app/monitor/api';
import useViewApi from '@/app/monitor/api/view';
import { ChartData, Dimension, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import {
  normalizeDisplayText,
  parseLegacyParamList,
  buildInstanceDisplayName,
  buildInstanceSearchTokens,
  formatMetricValue,
  buildSearchParams,
  getLatestChartValue,
  mergeChartSeries,
  buildPreviousPeriodTimeValues,
  getPeriodCompare,
  toMetricSeries,
  buildMetricItem,
  getCollectionStatus,
  buildCollectionStatusTimeline
} from '../../shared/utils';
import { GuideItem } from '../../shared/types';
import { StatCard, CollectionStatusCard, TitleWithGuide, InstanceSelector, DashboardPageHeader, DashboardInstanceCard } from '../../shared/widgets';
import styles from './simple-dashboard.module.scss';

export type SimpleMetricUnit = 'percent' | 'counts' | 'short' | 'cps' | 'ops' | 's' | 'ms' | 'ns' | 'bytes' | 'byteps' | 'msps' | 'none' | string;

export interface SimpleMetricConfig {
  name: string;
  display_name: string;
  description: string;
  unit: SimpleMetricUnit;
  query: string;
  color: string;
  dimensions?: Dimension[];
}

interface MetricSeries extends SimpleMetricConfig {
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
  formatter?: 'duration';
}

export interface SummaryCardConfig {
  title: string;
  guide: GuideItem[];
  metric: string;
  unit?: SimpleMetricUnit;
  color: string;
  icon: 'api' | 'clock' | 'database' | 'node' | 'thunder';
  compare?: boolean;
  footer?: SummaryFieldConfig[];
  hideTrend?: boolean;
  formatter?: 'duration';
}

export interface ChartConfig {
  title: string;
  subtitle: string;
  guide: GuideItem[];
  metric: string;
  series: Array<{ metric: string; label: string; color: string; unit?: SimpleMetricUnit }>;
}

export interface DetailPanelConfig {
  title: string;
  subtitle: string;
  rows: SummaryFieldConfig[];
}

export interface SimpleDashboardConfig {
  routeKey: string;
  pageTitle: string;
  objectFallbackName: string;
  instanceType: string;
  collectionStatusQuery: string;
  metrics: SimpleMetricConfig[];
  metaItems?: string[];
  summaryCards: SummaryCardConfig[];
  charts: ChartConfig[];
  details: DetailPanelConfig[];
}

const formatDuration = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0s';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
};

const getIcon = (type: SummaryCardConfig['icon']) => {
  const iconMap = {
    api: <ApiOutlined />,
    clock: <ClockCircleOutlined />,
    database: <DatabaseOutlined />,
    node: <NodeIndexOutlined />,
    thunder: <ThunderboltOutlined />
  };
  return iconMap[type];
};

export default function SimpleDashboard({ config }: { config: SimpleDashboardConfig }) {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  const router = useRouter();
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

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || config.objectFallbackName;
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || config.objectFallbackName;
  const rawInstanceId = searchParams.get('instance_id') || '';
  const parsedLegacyInstanceIds = parseLegacyParamList(rawInstanceId);
  const instanceId: React.Key = parsedLegacyInstanceIds[0] || rawInstanceId || '';
  const instanceName = searchParams.get('instance_name') || '--';
  const idValues = (() => {
    const explicitValues = parseLegacyParamList(searchParams.get('instance_id_values'));
    if (explicitValues.length > 0) return explicitValues;
    if (parsedLegacyInstanceIds.length > 0) return parsedLegacyInstanceIds;
    const normalizedInstanceId = normalizeDisplayText(String(instanceId));
    return normalizedInstanceId ? [normalizedInstanceId] : [];
  })();
  const instanceIdKeys = (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean);
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
  }, [monitorObjectId]);

  const idValuesKey = JSON.stringify(idValues);
  const currentInstanceCandidates = instanceOptions.filter(
    (item) => item.value === String(instanceId || '') || item.instanceIdValues.some((value) => idValues.includes(value))
  );
  const currentInstanceOption =
    currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) ||
    currentInstanceCandidates[0];
  const resolvedInstanceName = currentInstanceOption?.label || normalizedInstanceName || '--';
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
  }, [hasReadableInstanceName, idValuesKey, instanceId, instanceOptions, normalizedInstanceName]);
  const instanceSelectValue = currentInstanceOption?.value || (hasReadableInstanceName && instanceId ? String(instanceId) : undefined);

  const loadMetrics = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = config.metrics.filter((metric) => config.summaryCards.some((card) => card.compare && card.metric === metric.name));
        const metricResultsPromise = Promise.all(
          config.metrics.map((metric) =>
            getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues, undefined, false))
              .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
              .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
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
          ? Promise.all(
            compareMetrics.map((metric) =>
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues, undefined, false))
                .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
                .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
            )
          )
          : Promise.resolve([] as Array<readonly [string, MetricSeries]>);

        const [results, previousResults, collectionStatus] = await Promise.all([
          metricResultsPromise,
          previousMetricResultsPromise,
          collectionStatusPromise
        ]);
        setSeries(Object.fromEntries(results));
        setPreviousSeries(Object.fromEntries(previousResults));
        setCollectionStatusMetric(collectionStatus);
      } else {
        setSeries({});
        setPreviousSeries({});
        setCollectionStatusMetric(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isDashboardMode) {
      loadMetrics();
      return;
    }
    setLoading(false);
  }, [instanceId, idValuesKey, timeValues, isDashboardMode]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (frequence > 0 && isDashboardMode) {
      timerRef.current = setInterval(() => loadMetrics(true), frequence);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [frequence, timeValues, instanceId, idValuesKey, isDashboardMode]);

  const metricMap = useMemo(() => series, [series]);
  const previousMetricMap = useMemo(() => previousSeries, [previousSeries]);
  const getLatest = (name: string) => getLatestChartValue(metricMap[name]?.viewData || []);
  const hasMetricData = (name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  };
  const formatField = (field: SummaryFieldConfig) => {
    const value = getLatest(field.metric);
    if (!hasMetricData(field.metric)) return '--';
    if (field.formatter === 'duration') return formatDuration(value);
    const formatted = formatMetricValue(value, field.unit || metricMap[field.metric]?.unit || 'none');
    return `${formatted.value}${formatted.unit}`;
  };
  const formatMain = (card: SummaryCardConfig) => {
    if (!hasMetricData(card.metric)) return { value: '--', unit: '' };
    if (card.formatter === 'duration') return { value: formatDuration(getLatest(card.metric)), unit: '' };
    return formatMetricValue(getLatest(card.metric), card.unit || metricMap[card.metric]?.unit || 'none');
  };
  const getNoDataType = (...metricNames: string[]): 'empty' | 'error' => {
    const targets = metricNames.map((name) => metricMap[name]).filter(Boolean);
    return targets.length > 0 && targets.every((metric) => metric?.loadState === 'error') ? 'error' : 'empty';
  };

  const collectionStatus = getCollectionStatus(collectionStatusMetric, config.objectFallbackName);
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric?.loadState, collectionStatusMetric?.viewData);
  const chartsData = useMemo(
    () =>
      Object.fromEntries(
        config.charts.map((chart) => [
          chart.title,
          mergeChartSeries(chart.series.map((item) => ({ key: item.metric, label: item.label, data: metricMap[item.metric]?.viewData || [] })))
        ])
      ),
    [config.charts, metricMap]
  );

  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : config.pageTitle;
  const objectMetaItems = [
    <span key="object-name" className={styles.instanceMetaInline}>{objectDisplayText}</span>,
    ...(config.metaItems || []).map((item) => <span key={item} className={styles.instanceMetaInline}>{item}</span>),
    <span key="timezone" className={styles.instanceMetaInline}>时区: Asia/Shanghai</span>
  ];

  const onTimeChange = (val: number[], originValue: number | null) => setTimeValues({ timeRange: val, originValue });
  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    if (!arr?.[0] || !arr?.[1]) return;
    const start = dayjs(arr[0]).valueOf();
    const end = dayjs(arr[1]).valueOf();
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

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.pageHeader}>
          <DashboardPageHeader
            title={pageTitle}
            displayMode={displayMode}
            onDisplayModeChange={setDisplayMode}
            timeDefaultValue={timeDefaultValue}
            onTimeChange={onTimeChange}
            onFrequenceChange={setFrequence}
            onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
            onBack={goBack}
            styles={styles}
          />
          <DashboardInstanceCard
            instanceName={resolvedInstanceName}
            metaItems={objectMetaItems}
            icon={<DatabaseOutlined />}
            selectorValue={instanceSelectValue}
            selectorLoading={instanceLoading}
            selectorOptions={instanceSelectOptions}
            onInstanceChange={onInstanceChange}
            selectorPlaceholder={resolvedInstanceName !== '--' ? resolvedInstanceName : '选择实例'}
            selectorTitle={currentInstanceOption?.label || normalizedInstanceName || resolvedInstanceName}
            isDashboardMode={isDashboardMode}
            styles={styles}
          />
        </div>

        <div>
          {displayMode === 'dashboard' ? (
            <>
              <div className={styles.primaryGrid}>
                <CollectionStatusCard
                  status={collectionStatus}
                  timeline={collectionStatusTimeline}
                  guideItems={[
                    { label: '采集状态', detail: `展示最近一段时间内该 ${config.objectFallbackName} 实例监控采集是否正常、缺失或异常。` },
                    { label: '状态时间线', detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。' }
                  ]}
                  styles={styles}
                />
                {config.summaryCards.map((card) => {
                  const mainValue = formatMain(card);
                  const compare = card.compare
                    ? getPeriodCompare(getLatest(card.metric), getLatestChartValue(previousMetricMap[card.metric]?.viewData || []))
                    : null;
                  return (
                    <StatCard
                      key={card.title}
                      title={<TitleWithGuide title={card.title} items={card.guide} styles={styles} />}
                      value={mainValue.value}
                      unit={mainValue.unit}
                      icon={getIcon(card.icon)}
                      iconStyle={{ background: `${card.color}1f`, color: card.color }}
                      color={card.color}
                      footer={
                        <>
                          {(card.footer || []).map((field) => (
                            <span key={field.label}>{field.label} {formatField(field)}</span>
                          ))}
                        </>
                      }
                      compare={compare}
                      trendData={metricMap[card.metric]?.viewData || []}
                      hideTrend={card.hideTrend}
                      noDataType={getNoDataType(card.metric)}
                      styles={styles}
                    />
                  );
                })}
              </div>

              <div className={styles.chartGrid}>
                {config.charts.map((chart) => (
                  <div key={chart.title} className={styles.panel}>
                    <div className={styles.chartPanelHeader}>
                      <h3 className={styles.panelTitle}><TitleWithGuide title={chart.title} items={chart.guide} styles={styles} /></h3>
                      <div className={styles.panelSubTitle}>{chart.subtitle}</div>
                      <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                        {chart.series.map((item) => (
                          <span key={item.label} className={styles.chartLegendItem}>
                            <span className={styles.chartLegendDot} style={{ background: item.color }} />
                            {item.label}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className={styles.chartWrap}>
                      <EChartsLineChart
                        data={chartsData[chart.title] || []}
                        metric={buildMetricItem(metricMap[chart.metric] || config.metrics.find((metric) => metric.name === chart.metric) || config.metrics[0])}
                        seriesStyles={chart.series.map((item) => ({ color: item.color, unit: item.unit || metricMap[item.metric]?.unit || '' }))}
                        allowSelect={false}
                        onXRangeChange={onXRangeChange}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className={styles.detailGrid}>
                {config.details.map((panel) => (
                  <div key={panel.title} className={styles.panel}>
                    <h3 className={styles.panelTitle}>{panel.title}</h3>
                    <div className={styles.panelSubTitle}>{panel.subtitle}</div>
                    {panel.rows.map((row) => (
                      <div key={row.label} className={styles.detailMetricRow}>
                        <span>{row.label}</span>
                        <span className={styles.detailMetricValue}>{formatField(row)}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className={styles.metricsMode}>
              <div className={`${styles.panel} ${styles.fullPanel}`}>
                <div className={styles.sectionHeading}>
                  <h3 className={styles.panelTitle}>
                    <TitleWithGuide title="监控指标全量" items={[{ label: '监控指标全景', detail: '承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' }]} styles={styles} />
                  </h3>
                </div>
                <MetricViews
                  monitorObjectId={monitorObjectId}
                  monitorObjectName={monitorObjectName}
                  instanceId={instanceId}
                  instanceName={resolvedInstanceName}
                  idValues={idValues}
                  externalTimeValues={timeValues}
                  externalTimeDefaultValue={timeDefaultValue}
                  externalFrequence={frequence}
                  externalRefreshSignal={metricsRefreshSignal}
                  hideTimeSelector
                  onExternalXRangeChange={onXRangeChange}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
