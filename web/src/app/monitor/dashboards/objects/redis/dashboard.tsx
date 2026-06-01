'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Empty, Tooltip } from 'antd';
import {
  ClockCircleOutlined,
  DatabaseOutlined,
  NodeIndexOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import EChartsLineChart from '../../shared/widgets/echarts-line-chart';
import { InlineRingChart } from '../../shared/widgets/inline-ring-chart';
import {
  StatCard,
  CollectionStatusCard,
  TitleWithGuide,
  GuideTooltipContent,
  InstanceSelector,
  DashboardPageHeader,
  DashboardInstanceCard
} from '../../shared/widgets';
import {
  formatMetricValue,
  buildSearchParams,
  getLatestChartValue,
  buildPreviousPeriodTimeValues,
  getPeriodCompare,
  normalizeDisplayText,
  buildInstanceDisplayName,
  buildInstanceSearchTokens,
  parseLegacyParamList,
  buildCollectionStatusTimeline,
  toMetricSeries,
  buildMetricItem,
  mergeChartSeries,
  getCollectionStatus,
  runWithConcurrency
} from '../../shared/utils';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import useMonitorApi from '@/app/monitor/api';
import { useTranslation } from '@/utils/i18n';
import { ChartData, MetricItem, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import {
  DASHBOARD_METRICS,
  REDIS_COLLECTION_STATUS_QUERY,
  TREND_LEGENDS
} from './config';
import { MetricSeries, MetricUnit, RedisMetricConfig } from './types';
import styles from './index.module.scss';

interface RedisInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
}

const RAW_VALUE_METRICS = new Set([
  'redis_uptime',
  'redis_used_memory',
  'redis_maxmemory',
  'redis_clients',
  'redis_blocked_clients'
]);

const METRIC_QUERY_CONCURRENCY = 6;

const REDIS_METRIC_GROUPS = [
  {
    key: 'summary',
    names: [
      'redis_uptime',
      'redis_used_memory',
      'redis_maxmemory',
      'redis_memory_utilization',
      'redis_instantaneous_ops_per_sec',
      'redis_keyspace_hitrate',
      'redis_clients',
      'redis_blocked_clients',
      'redis_rejected_connections_rate'
    ]
  },
  {
    key: 'trends',
    names: [
      'redis_mem_fragmentation_ratio',
      'redis_total_commands_processed_rate',
      'redis_keyspace_hits_rate',
      'redis_keyspace_misses_rate',
      'redis_total_net_input_bytes_rate',
      'redis_total_net_output_bytes_rate',
      'redis_expired_keys_rate',
      'redis_evicted_keys_rate'
    ]
  }
];

export default function RedisDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayMode, setDisplayMode] = useState<'dashboard' | 'metrics'>('dashboard');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({
    timeRange: [],
    originValue: 15
  });
  const [timeDefaultValue, setTimeDefaultValue] = useState<TimeSelectorDefaultValue>({
    selectValue: 15,
    rangePickerVaule: null
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [series, setSeries] = useState<Record<string, MetricSeries>>({});
  const [previousSeries, setPreviousSeries] = useState<Record<string, MetricSeries>>({});
  const [collectionStatusMetric, setCollectionStatusMetric] = useState<MetricSeries | null>(null);
  const [instanceOptions, setInstanceOptions] = useState<RedisInstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);
  const loadSeqRef = useRef(0);

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || 'Redis';
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || 'Redis';
  const rawInstanceId = searchParams.get('instance_id') || '';
  const parsedLegacyInstanceIds = parseLegacyParamList(rawInstanceId);
  const instanceId: React.Key = parsedLegacyInstanceIds[0] || rawInstanceId || '';
  const instanceName = searchParams.get('instance_name') || '--';
  const idValues = (() => {
    const explicitValues = parseLegacyParamList(searchParams.get('instance_id_values'));
    if (explicitValues.length > 0) {
      return explicitValues;
    }
    if (parsedLegacyInstanceIds.length > 0) {
      return parsedLegacyInstanceIds;
    }
    const normalizedInstanceId = normalizeDisplayText(String(instanceId));
    return normalizedInstanceId ? [normalizedInstanceId] : [];
  })();
  const instanceIdKeys = (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean);
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || 'Redis';
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
        if (!active) {
          return;
        }
        const uniqueOptions = new Map<string, RedisInstanceOption>();
        (data?.results || []).forEach((item: any) => {
          const value = String(item.instance_id || '');
          if (!value || uniqueOptions.has(value)) {
            return;
          }
          const label = buildInstanceDisplayName(item);
          uniqueOptions.set(value, {
            label,
            value,
            instanceIdValues:
              Array.isArray(item.instance_id_values) && item.instance_id_values.length ? item.instance_id_values : [value],
            searchTokens: buildInstanceSearchTokens(item, label)
          });
        });
        setInstanceOptions(Array.from(uniqueOptions.values()));
      } catch {
        if (active) {
          setInstanceOptions([]);
        }
      } finally {
        if (active) {
          setInstanceLoading(false);
        }
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
  const currentInstanceOption = currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) || currentInstanceCandidates[0];
  const resolvedInstanceName =
    currentInstanceOption?.label || normalizedInstanceName || normalizeDisplayText(String(instanceId)) || normalizeDisplayText(idValues[0]) || '--';

  const loadMetricGroup = async (metricNames: readonly string[]) => {
    const metrics = metricNames
      .map((name) => DASHBOARD_METRICS.find((m) => m.name === name))
      .filter((m): m is RedisMetricConfig => Boolean(m));
    return runWithConcurrency(
      metrics,
      METRIC_QUERY_CONCURRENCY,
      async (metric) =>
        getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues, RAW_VALUE_METRICS))
          .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
          .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
    );
  };

  const loadMetrics = async (silent = false) => {
    const loadSeq = loadSeqRef.current + 1;
    loadSeqRef.current = loadSeq;

    if (!silent) {
      setLoading(true);
    }

    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = DASHBOARD_METRICS.filter((metric) =>
          ['redis_memory_utilization', 'redis_instantaneous_ops_per_sec', 'redis_keyspace_hitrate', 'redis_clients'].includes(metric.name)
        );

        const summaryResultsPromise = loadMetricGroup(REDIS_METRIC_GROUPS[0].names);

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(
          buildSearchParams(REDIS_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues, RAW_VALUE_METRICS)
        )
          .then((result) =>
            toMetricSeries<RedisMetricConfig>(
              {
                name: 'redis_collection_status',
                display_name: '采集状态',
                description: 'Redis 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts' as MetricUnit,
                query: REDIS_COLLECTION_STATUS_QUERY,
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
                name: 'redis_collection_status',
                display_name: '采集状态',
                description: 'Redis 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts' as MetricUnit,
                query: REDIS_COLLECTION_STATUS_QUERY,
                color: '#27c274',
                viewData: [],
                loadState: 'error' as const
              }) satisfies MetricSeries
          );

        const previousMetricResultsPromise = previousTimeValues
          ? runWithConcurrency(
            compareMetrics,
            METRIC_QUERY_CONCURRENCY,
            async (metric) =>
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues, RAW_VALUE_METRICS))
                .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
                .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
          : Promise.resolve([] as Array<readonly [string, MetricSeries]>);

        const [summaryResults, previousResults, collectionStatus] = await Promise.all([
          summaryResultsPromise,
          previousMetricResultsPromise,
          collectionStatusPromise
        ]);

        if (loadSeqRef.current !== loadSeq) return;

        setSeries((prev) => (silent ? { ...prev, ...Object.fromEntries(summaryResults) } : Object.fromEntries(summaryResults)));
        setPreviousSeries(Object.fromEntries(previousResults));
        setCollectionStatusMetric(collectionStatus);

        if (!silent) setLoading(false);

        REDIS_METRIC_GROUPS.slice(1).forEach((group) => {
          loadMetricGroup(group.names).then((results) => {
            if (loadSeqRef.current !== loadSeq) return;
            setSeries((prev) => ({ ...prev, ...Object.fromEntries(results) }));
          });
        });
      } else {
        setSeries({});
        setPreviousSeries({});
        setCollectionStatusMetric(null);
        if (!silent) setLoading(false);
      }
    } catch {
      if (loadSeqRef.current === loadSeq && !silent) setLoading(false);
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
      timerRef.current = setInterval(() => {
        loadMetrics(true);
      }, frequence);
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
  const getPreviousLatest = (name: string) => getLatestChartValue(previousMetricMap[name]?.viewData || []);
  const hasMetricData = (name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  };
  const renderMetricValue = (name: string, value: string) => (hasMetricData(name) ? value : '--');

  const uptimeValue = getLatest('redis_uptime');
  const usedMemoryValue = getLatest('redis_used_memory');
  const maxMemoryValue = getLatest('redis_maxmemory');
  const memoryUtilValue = getLatest('redis_memory_utilization');
  const fragmentationValue = getLatest('redis_mem_fragmentation_ratio');
  const opsValue = getLatest('redis_instantaneous_ops_per_sec');
  const commandRateValue = getLatest('redis_total_commands_processed_rate');
  const hitRateValue = getLatest('redis_keyspace_hitrate');
  const hitsRateValue = getLatest('redis_keyspace_hits_rate');
  const missesRateValue = getLatest('redis_keyspace_misses_rate');
  const clientsValue = getLatest('redis_clients');
  const blockedClientsValue = getLatest('redis_blocked_clients');
  const expiredRateValue = getLatest('redis_expired_keys_rate');
  const evictedRateValue = getLatest('redis_evicted_keys_rate');
  const rejectedRateValue = getLatest('redis_rejected_connections_rate');

  const collectionStatus = getCollectionStatus(collectionStatusMetric, 'Redis');
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric?.loadState, collectionStatusMetric?.viewData);
  const metricEmptyText = collectionStatus.label === '异常' ? '查询失败' : '暂无采集数据';

  const uptimeDisplay = formatMetricValue(uptimeValue, 's');
  const usedMemoryDisplay = formatMetricValue(usedMemoryValue, 'bytes');
  const maxMemoryDisplay = formatMetricValue(maxMemoryValue, 'bytes');
  const memoryUtilDisplay = formatMetricValue(memoryUtilValue, 'percent');
  const fragmentationDisplay = formatMetricValue(fragmentationValue, 'none');
  const opsDisplay = formatMetricValue(opsValue, 'cps');
  const commandRateDisplay = formatMetricValue(commandRateValue, 'cps');
  const hitRateDisplay = formatMetricValue(hitRateValue, 'percent');
  const hitsRateDisplay = formatMetricValue(hitsRateValue, 'cps');
  const missesRateDisplay = formatMetricValue(missesRateValue, 'cps');
  const clientsDisplay = formatMetricValue(clientsValue, 'counts');
  const blockedClientsDisplay = formatMetricValue(blockedClientsValue, 'counts');
  const expiredDisplay = formatMetricValue(expiredRateValue, 'cps');
  const evictedDisplay = formatMetricValue(evictedRateValue, 'cps');
  const rejectedDisplay = formatMetricValue(rejectedRateValue, 'cps');

  const memoryCompare = maxMemoryValue > 0 ? getPeriodCompare(memoryUtilValue, getPreviousLatest('redis_memory_utilization')) : null;
  const opsCompare = getPeriodCompare(opsValue, getPreviousLatest('redis_instantaneous_ops_per_sec'));
  const hitRateCompare = getPeriodCompare(hitRateValue, getPreviousLatest('redis_keyspace_hitrate'));
  const clientCompare = getPeriodCompare(clientsValue, getPreviousLatest('redis_clients'));

  const uptimeStartedAt = Number.isFinite(uptimeValue) && uptimeValue >= 0 ? dayjs().subtract(Math.floor(uptimeValue), 'second').format('YYYY-MM-DD HH:mm:ss') : metricEmptyText;
  const uptimeStatusGuide = [
    { label: '运行时长', detail: '基于 redis_uptime 计算实例自上次启动以来持续运行的时间。' },
    { label: '启动时间', detail: '表示当前进程启动的大致时间点。' }
  ];

  const opsTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'redis_instantaneous_ops_per_sec',
          label: '实时 OPS',
          displayName: '实时 OPS',
          data: metricMap.redis_instantaneous_ops_per_sec?.viewData || []
        },
        {
          key: 'redis_total_commands_processed_rate',
          label: '命令处理速率',
          displayName: '命令处理速率',
          data: metricMap.redis_total_commands_processed_rate?.viewData || []
        }
      ]),
    [metricMap.redis_instantaneous_ops_per_sec?.viewData, metricMap.redis_total_commands_processed_rate?.viewData]
  );

  const memoryTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'redis_used_memory',
          label: '已用内存',
          displayName: '已用内存',
          data: metricMap.redis_used_memory?.viewData || []
        },
        {
          key: 'redis_maxmemory',
          label: '内存上限',
          displayName: '内存上限',
          data: metricMap.redis_maxmemory?.viewData || []
        }
      ]),
    [metricMap.redis_used_memory?.viewData, metricMap.redis_maxmemory?.viewData]
  );

  const networkTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'redis_total_net_input_bytes_rate',
          label: '入流量',
          displayName: '入流量',
          data: metricMap.redis_total_net_input_bytes_rate?.viewData || []
        },
        {
          key: 'redis_total_net_output_bytes_rate',
          label: '出流量',
          displayName: '出流量',
          data: metricMap.redis_total_net_output_bytes_rate?.viewData || []
        }
      ]),
    [metricMap.redis_total_net_input_bytes_rate?.viewData, metricMap.redis_total_net_output_bytes_rate?.viewData]
  );


  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : 'Redis 监控仪表盘';
  const hasDashboardContent = DASHBOARD_METRICS.length > 0;
  const showEmpty = isDashboardMode ? !hasDashboardContent : false;

  const currentInstanceText = resolvedInstanceName;
  const instanceMetaItems = [
    <span key="object-name" className={styles.instanceMetaInline}>{objectDisplayText}</span>,
    <span key="timezone" className={styles.instanceMetaInline}>时区: Asia/Shanghai</span>
  ];

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({ timeRange: val, originValue });
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    if (!arr?.[0] || !arr?.[1]) {
      return;
    }
    const start = dayjs(arr[0]).valueOf();
    const end = dayjs(arr[1]).valueOf();
    if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
      return;
    }
    setTimeDefaultValue((prev) => ({
      ...prev,
      rangePickerVaule: arr,
      selectValue: 0
    }));
    setTimeValues({
      timeRange: [start, end],
      originValue: 0
    });
  };

  const onFrequenceChange = (val: number) => setFrequence(val);
  const goBack = () => router.push('/monitor/view');

  const onInstanceChange = (value: string) => {
    const target = instanceOptions.find((item) => item.value === value);
    const params = new URLSearchParams(searchParams.toString());
    params.set('instance_id', value);
    params.set('instance_name', String(target?.label || value));
    params.set('instance_id_values', (target?.instanceIdValues || [value]).join(','));
    router.push(`/monitor/view/dashboard/redis?${params.toString()}`);
  };

  const getNoDataType = (...metricNames: string[]): 'empty' | 'error' => {
    if (metricNames.includes('redis_collection_status')) {
      return collectionStatusMetric?.loadState === 'error' ? 'error' : 'empty';
    }
    const targets = metricNames.map((name) => metricMap[name]).filter(Boolean);
    return targets.length > 0 && targets.every((metric) => metric?.loadState === 'error') ? 'error' : 'empty';
  };

  const memoryGuide = [
    { label: '内存使用率', detail: '表示已用内存占配置上限的比例。' },
    { label: '排查建议', detail: '当使用率接近上限时，应同时查看键驱逐、内存碎片率和网络流量。' }
  ];
  const opsGuide = [
    { label: '实时 OPS', detail: '表示 Redis 当前每秒处理的命令数量。' },
    { label: '关联判断', detail: 'OPS 持续抬升时，需要结合网络流量、命中率和客户端连接一起判断压力来源。' }
  ];
  const hitGuide = [
    { label: '缓存命中率', detail: '表示键命中占总键访问的比例。' },
    { label: '关联判断', detail: '命中率降低时，应结合命中频率、未命中频率和内存使用率一起分析。' }
  ];
  const clientGuide = [
    { label: '客户端连接数', detail: '表示当前活跃的客户端连接总量。' },
    { label: '关联判断', detail: '如果连接数升高且阻塞客户端增加，需要同时关注慢命令和网络出流量。' }
  ];
  const uptimeGuide = [
    { label: '运行时长', detail: '表示 Redis 进程自上次启动以来的持续运行时间。' },
    { label: '启动时间', detail: '用于辅助判断实例是否近期发生过重启。' }
  ];
  const opsTrendGuide = [
    { label: '命令吞吐趋势', detail: '同时展示实时 OPS 和命令处理速率，判断 Redis 当前吞吐变化。' }
  ];
  const memoryTrendGuide = [
    { label: '内存趋势', detail: '同时展示已用内存与内存上限，判断实例是否逼近容量边界。' }
  ];
  const networkTrendGuide = [
    { label: '网络流量趋势', detail: '同时展示 Redis 的网络入流量和出流量，判断请求与返回压力。' }
  ];
  const cacheDetailGuide = [
    { label: '缓存访问概览', detail: '集中展示命中率、命中频率和未命中频率，判断缓存是否有效工作。' }
  ];
  const clientDetailGuide = [
    { label: '客户端与阻塞', detail: '展示客户端总量、阻塞连接和连接拒绝频率，判断连接层是否存在拥塞。' }
  ];
  const keyLifecycleGuide = [
    { label: '键生命周期', detail: '展示过期键与驱逐键频率，判断缓存淘汰和生命周期行为是否异常。' }
  ];
  const memoryDetailGuide = [
    { label: '内存与碎片', detail: '展示已用内存、内存上限、使用率与碎片率。' },
    { label: '碎片率', detail: '碎片率过高通常意味着 Redis 内存分配与回收效率下降。' }
  ];
  const metricsOverviewGuide = [
    { label: '监控指标全景', detail: '这里承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' }
  ];

  const fragmentationTone = !hasMetricData('redis_mem_fragmentation_ratio')
    ? 'normal'
    : fragmentationValue >= 1.5
      ? 'danger'
      : fragmentationValue >= 1.2
        ? 'warn'
        : 'normal';

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
            onFrequenceChange={onFrequenceChange}
            onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
            onBack={goBack}
            styles={styles}
          />

          <DashboardInstanceCard
            instanceName={currentInstanceText}
            metaItems={instanceMetaItems}
            icon={<DatabaseOutlined />}
            selectorValue={currentInstanceOption?.value || (instanceId ? String(instanceId) : undefined)}
            selectorLoading={instanceLoading}
            selectorOptions={instanceOptions}
            onInstanceChange={onInstanceChange}
            selectorPlaceholder="选择实例"
            selectorTitle={currentInstanceOption?.label || resolvedInstanceName}
            isDashboardMode={isDashboardMode}
            styles={styles}
          />
        </div>

        <div>
          {showEmpty ? (
            <div className={styles.empty}>
              <Empty description={t('暂无数据')} />
            </div>
          ) : (
            <>
              {displayMode === 'dashboard' ? (
                <>
                  <div className={styles.primaryGrid}>
                    <CollectionStatusCard styles={styles} status={collectionStatus} timeline={collectionStatusTimeline} />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="Redis 运行时长" items={uptimeGuide} className={styles.statTitleWithGuide} />}
                      value={hasMetricData('redis_uptime') ? `${uptimeDisplay.value}${uptimeDisplay.unit}` : '--'}
                      unit=""
                      icon={<ClockCircleOutlined />}
                      iconStyle={{ background: 'rgba(89, 126, 247, 0.12)', color: '#597ef7' }}
                      color="#597ef7"
                      className={styles.statCardRelaxed}
                      bodyClassName={styles.statBodyRelaxed}
                      footer={<span>启动时间 {uptimeStartedAt}</span>}
                      hideTrend
                      noDataType={getNoDataType('redis_uptime')}
                      extra={
                        <div className={`${styles.uptimeStatus} ${styles.uptimeStatusSuccess}`}>
                          <span className={styles.uptimeStatusDot} />
                          <div className={styles.uptimeStatusMainWrap}>
                            <span className={styles.uptimeStatusMain}>运行正常</span>
                            <Tooltip overlayClassName="lightMetricTooltip" title={<GuideTooltipContent styles={styles} items={uptimeStatusGuide} />}>
                              <ClockCircleOutlined className={styles.uptimeStatusInfoIcon} />
                            </Tooltip>
                          </div>
                        </div>
                      }
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="内存使用率" items={memoryGuide} className={styles.statTitleWithGuide} />}
                      value={maxMemoryValue > 0 && hasMetricData('redis_memory_utilization') ? memoryUtilDisplay.value : '--'}
                      unit={maxMemoryValue > 0 && hasMetricData('redis_memory_utilization') ? memoryUtilDisplay.unit : ''}
                      icon={<DatabaseOutlined />}
                      iconStyle={{ background: 'rgba(255, 138, 31, 0.12)', color: '#ff8a1f' }}
                      color="#ff8a1f"
                      footer={
                        <>
                          <span>已用 {renderMetricValue('redis_used_memory', `${usedMemoryDisplay.value}${usedMemoryDisplay.unit}`)}</span>
                          <span>上限 {maxMemoryValue > 0 && hasMetricData('redis_maxmemory') ? `${maxMemoryDisplay.value}${maxMemoryDisplay.unit}` : '未配置'}</span>
                        </>
                      }
                      compare={memoryCompare}
                      trendData={metricMap.redis_memory_utilization?.viewData || []}
                      noDataType={getNoDataType('redis_memory_utilization')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="实时 OPS" items={opsGuide} className={styles.statTitleWithGuide} />}
                      value={renderMetricValue('redis_instantaneous_ops_per_sec', opsDisplay.value)}
                      unit={hasMetricData('redis_instantaneous_ops_per_sec') ? opsDisplay.unit : ''}
                      icon={<ThunderboltOutlined />}
                      iconStyle={{ background: 'rgba(39, 194, 116, 0.12)', color: '#27c274' }}
                      color="#27c274"
                      footer={<span>命令处理 {renderMetricValue('redis_total_commands_processed_rate', `${commandRateDisplay.value}${commandRateDisplay.unit}`)}</span>}
                      compare={opsCompare}
                      trendData={metricMap.redis_instantaneous_ops_per_sec?.viewData || []}
                      noDataType={getNoDataType('redis_instantaneous_ops_per_sec')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="缓存命中率" items={hitGuide} className={styles.statTitleWithGuide} />}
                      value={renderMetricValue('redis_keyspace_hitrate', hitRateDisplay.value)}
                      unit={hasMetricData('redis_keyspace_hitrate') ? hitRateDisplay.unit : ''}
                      icon={<DatabaseOutlined />}
                      iconStyle={{ background: 'rgba(138, 92, 255, 0.12)', color: '#8a5cff' }}
                      color="#8a5cff"
                      footer={
                        <>
                          <span>命中 {renderMetricValue('redis_keyspace_hits_rate', `${hitsRateDisplay.value}${hitsRateDisplay.unit}`)}</span>
                          <span>未命中 {renderMetricValue('redis_keyspace_misses_rate', `${missesRateDisplay.value}${missesRateDisplay.unit}`)}</span>
                        </>
                      }
                      compare={hitRateCompare}
                      trendData={metricMap.redis_keyspace_hitrate?.viewData || []}
                      noDataType={getNoDataType('redis_keyspace_hitrate')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="客户端连接数" items={clientGuide} className={styles.statTitleWithGuide} />}
                      value={renderMetricValue('redis_clients', clientsDisplay.value)}
                      unit=""
                      icon={<NodeIndexOutlined />}
                      iconStyle={{ background: 'rgba(47, 107, 255, 0.12)', color: '#2f6bff' }}
                      color="#2f6bff"
                      footer={
                        <>
                          <span>阻塞客户端 {renderMetricValue('redis_blocked_clients', blockedClientsDisplay.value)}</span>
                          <span>拒绝频率 {renderMetricValue('redis_rejected_connections_rate', `${rejectedDisplay.value}${rejectedDisplay.unit}`)}</span>
                        </>
                      }
                      compare={clientCompare}
                      trendData={metricMap.redis_clients?.viewData || []}
                      noDataType={getNoDataType('redis_clients')}
                    />
                  </div>

                  <div className={styles.mainTrendGrid}>
                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                          <TitleWithGuide styles={styles} title="命令吞吐趋势" items={opsTrendGuide} className={styles.panelTitleWithGuide} />
                        </h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>实时 OPS 与平均命令处理</div>
                        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                          {TREND_LEGENDS.ops.map((item) => (
                            <span key={item.label} className={styles.chartLegendItem}>
                              <span className={styles.chartLegendDot} style={{ background: item.color }} />
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className={styles.chartWrap}>
                        <EChartsLineChart
                          data={opsTrendData}
                          metric={buildMetricItem(metricMap.redis_instantaneous_ops_per_sec || { ...DASHBOARD_METRICS[5], viewData: [], loadState: 'success' })}
                          seriesStyles={[
                            { color: TREND_LEGENDS.ops[0].color, unit: 'cps' },
                            { color: TREND_LEGENDS.ops[1].color, unit: 'cps' }
                          ]}
                          allowSelect={false}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                          <TitleWithGuide styles={styles} title="内存趋势" items={memoryTrendGuide} className={styles.panelTitleWithGuide} />
                        </h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>
                          已用内存与配置上限
                        </div>
                        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                          {TREND_LEGENDS.memory.map((item) => (
                            <span key={item.label} className={styles.chartLegendItem}>
                              <span
                                className={item.dashed ? styles.chartLegendDash : styles.chartLegendDot}
                                style={item.dashed ? { borderTopColor: item.color } : { background: item.color }}
                              />
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className={styles.chartWrap}>
                        <EChartsLineChart
                          data={memoryTrendData}
                          metric={buildMetricItem(metricMap.redis_used_memory || { ...DASHBOARD_METRICS[1], viewData: [], loadState: 'success' })}
                          seriesStyles={[
                            { color: TREND_LEGENDS.memory[0].color, unit: 'bytes' },
                            { color: TREND_LEGENDS.memory[1].color, strokeDasharray: '5 5', unit: 'bytes' }
                          ]}
                          allowSelect={false}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                          <TitleWithGuide styles={styles} title="网络流量趋势" items={networkTrendGuide} className={styles.panelTitleWithGuide} />
                        </h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>
                          请求接收与结果返回
                        </div>
                        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                          {TREND_LEGENDS.network.map((item) => (
                            <span key={item.label} className={styles.chartLegendItem}>
                              <span className={styles.chartLegendDot} style={{ background: item.color }} />
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className={styles.chartWrap}>
                        <EChartsLineChart
                          data={networkTrendData}
                          metric={buildMetricItem(metricMap.redis_total_net_input_bytes_rate || { ...DASHBOARD_METRICS[10], viewData: [], loadState: 'success' })}
                          seriesStyles={[
                            { color: TREND_LEGENDS.network[0].color, unit: 'byteps' },
                            { color: TREND_LEGENDS.network[1].color, unit: 'byteps' }
                          ]}
                          allowSelect={false}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>
                  </div>

                  <div className={styles.detailGrid}>
                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="内存占用分布" items={memoryGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>已用与剩余内存占比</div>
                        </div>
                      </div>
                      <div className={styles.ringCard}>
                        <div className={styles.ringChartWrap}>
                          <InlineRingChart
                            data={(() => {
                              const used = hasMetricData('redis_used_memory') ? usedMemoryValue : 0;
                              const max = hasMetricData('redis_maxmemory') && maxMemoryValue > 0 ? maxMemoryValue : used;
                              const free = Math.max(max - used, 0);
                              return [
                                { name: '已用', value: used, color: '#ff8a1f' },
                                { name: '剩余', value: free, color: '#e8f0fe' }
                              ];
                            })()}
                          />
                          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                            <div className={styles.ringValue}>{maxMemoryValue > 0 && hasMetricData('redis_memory_utilization') ? `${memoryUtilDisplay.value}%` : '--'}</div>
                            <div className={styles.ringCaption}>使用率</div>
                          </div>
                        </div>
                        <div className={styles.ringInfoPanel}>
                          <div className={styles.metricList}>
                            <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`}>
                              <span className={styles.metricKey}>
                                <span className={styles.metricLabelGroup}>
                                  <span className={styles.metricDot} style={{ background: '#ff8a1f' }} />
                                  <span className={styles.metricName}>已用内存</span>
                                </span>
                              </span>
                              <span className={styles.metricValueGroup}>
                                <span className={styles.metricPercent}>{renderMetricValue('redis_used_memory', `${usedMemoryDisplay.value}${usedMemoryDisplay.unit}`)}</span>
                              </span>
                            </div>
                            <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`}>
                              <span className={styles.metricKey}>
                                <span className={styles.metricLabelGroup}>
                                  <span className={styles.metricDot} style={{ background: '#e8f0fe' }} />
                                  <span className={styles.metricName}>内存上限</span>
                                </span>
                              </span>
                              <span className={styles.metricValueGroup}>
                                <span className={styles.metricPercent}>{maxMemoryValue > 0 && hasMetricData('redis_maxmemory') ? `${maxMemoryDisplay.value}${maxMemoryDisplay.unit}` : '未配置'}</span>
                              </span>
                            </div>
                            <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`}>
                              <span className={styles.metricKey}>
                                <span className={styles.metricLabelGroup}>
                                  <span className={styles.metricDot} style={{ background: '#faad14' }} />
                                  <span className={styles.metricName}>碎片率</span>
                                </span>
                              </span>
                              <span className={styles.metricValueGroup}>
                                <span className={styles.metricPercent}>{renderMetricValue('redis_mem_fragmentation_ratio', fragmentationDisplay.value)}</span>
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="命中分布" items={hitGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>命中与未命中频率占比</div>
                        </div>
                      </div>
                      <div className={styles.ringCard}>
                        <div className={styles.ringChartWrap}>
                          <InlineRingChart
                            data={[
                              { name: '命中', value: hasMetricData('redis_keyspace_hits_rate') ? hitsRateValue : 0, color: '#8a5cff' },
                              { name: '未命中', value: hasMetricData('redis_keyspace_misses_rate') ? missesRateValue : 0, color: '#ffccc7' }
                            ]}
                          />
                          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                            <div className={styles.ringValue}>{hasMetricData('redis_keyspace_hitrate') ? `${hitRateDisplay.value}%` : '--'}</div>
                            <div className={styles.ringCaption}>命中率</div>
                          </div>
                        </div>
                        <div className={styles.ringInfoPanel}>
                          <div className={styles.metricList}>
                            <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`}>
                              <span className={styles.metricKey}>
                                <span className={styles.metricLabelGroup}>
                                  <span className={styles.metricDot} style={{ background: '#8a5cff' }} />
                                  <span className={styles.metricName}>键命中频率</span>
                                </span>
                              </span>
                              <span className={styles.metricValueGroup}>
                                <span className={styles.metricPercent}>{renderMetricValue('redis_keyspace_hits_rate', `${hitsRateDisplay.value}${hitsRateDisplay.unit}`)}</span>
                              </span>
                            </div>
                            <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`}>
                              <span className={styles.metricKey}>
                                <span className={styles.metricLabelGroup}>
                                  <span className={styles.metricDot} style={{ background: '#ffccc7' }} />
                                  <span className={styles.metricName}>键未命中频率</span>
                                </span>
                              </span>
                              <span className={styles.metricValueGroup}>
                                <span className={styles.metricPercent}>{renderMetricValue('redis_keyspace_misses_rate', `${missesRateDisplay.value}${missesRateDisplay.unit}`)}</span>
                              </span>
                            </div>
                            <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`}>
                              <span className={styles.metricKey}>
                                <span className={styles.metricLabelGroup}>
                                  <span className={styles.metricDot} style={{ background: '#27c274' }} />
                                  <span className={styles.metricName}>命中率</span>
                                </span>
                              </span>
                              <span className={styles.metricValueGroup}>
                                <span className={styles.metricPercent}>{renderMetricValue('redis_keyspace_hitrate', `${hitRateDisplay.value}${hitRateDisplay.unit}`)}</span>
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="客户端状态" items={clientGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>连接分布与阻塞情况</div>
                        </div>
                      </div>
                      <div className={`${styles.bars} ${styles.compactBars} ${styles.barsFull}`}>
                        {(() => {
                          const normalClients = Math.max(clientsValue - blockedClientsValue, 0);
                          const maxVal = Math.max(clientsValue, 1);
                          return [
                            { label: '正常连接', value: normalClients, display: hasMetricData('redis_clients') ? normalClients.toFixed(0) : '--', color: '#2f6bff', max: maxVal },
                            { label: '阻塞客户端', value: blockedClientsValue, display: renderMetricValue('redis_blocked_clients', blockedClientsDisplay.value), color: '#fa8c16', max: maxVal },
                            { label: '连接拒绝频率', value: rejectedRateValue, display: renderMetricValue('redis_rejected_connections_rate', `${rejectedDisplay.value}${rejectedDisplay.unit}`), color: '#ff4d4f', max: Math.max(rejectedRateValue, clientsValue, 1) }
                          ];
                        })().map((item) => (
                          <div key={item.label} className={styles.barRow}>
                            <div className={styles.barLabel}>{item.label}</div>
                            <div className={styles.barTrack}>
                              <div
                                className={styles.barFill}
                                style={{ width: `${Math.min((item.value / item.max) * 100, 100)}%`, background: item.color }}
                              />
                            </div>
                            <div className={styles.barValue}>{item.display}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className={styles.detailGrid}>
                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.detailCard}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="缓存访问概览" items={cacheDetailGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>命中率与键访问结果</div>
                        </div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>缓存命中率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_keyspace_hitrate', `${hitRateDisplay.value}${hitRateDisplay.unit}`)}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>键命中频率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_keyspace_hits_rate', `${hitsRateDisplay.value}${hitsRateDisplay.unit}`)}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>键未命中频率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_keyspace_misses_rate', `${missesRateDisplay.value}${missesRateDisplay.unit}`)}</span></div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.detailCard}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="客户端与阻塞" items={clientDetailGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>连接总量与阻塞情况</div>
                        </div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>当前连接</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_clients', clientsDisplay.value)}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>阻塞客户端</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_blocked_clients', blockedClientsDisplay.value)}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>连接拒绝频率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_rejected_connections_rate', `${rejectedDisplay.value}${rejectedDisplay.unit}`)}</span></div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.detailCard}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="键生命周期" items={keyLifecycleGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>过期与驱逐行为</div>
                        </div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>键过期频率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_expired_keys_rate', `${expiredDisplay.value}${expiredDisplay.unit}`)}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>键驱逐频率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_evicted_keys_rate', `${evictedDisplay.value}${evictedDisplay.unit}`)}</span></div>
                        <div
                          className={`${styles.fragmentationWarning} ${
                            evictedRateValue > 0 ? styles.fragmentationWarningDanger : styles.fragmentationWarningNormal
                          }`}
                        >
                          {evictedRateValue > 0 ? '出现驱逐，通常说明内存接近上限。' : '当前未观察到明显驱逐。'}
                        </div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.detailCard}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide styles={styles} title="内存与碎片" items={memoryDetailGuide} className={styles.panelTitleWithGuide} /></h3>
                          <div className={styles.panelSubTitle}>容量边界与分配效率</div>
                        </div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>已用内存</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_used_memory', `${usedMemoryDisplay.value}${usedMemoryDisplay.unit}`)}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>内存上限</span><span className={styles.detailMetricValue}>{maxMemoryValue > 0 && hasMetricData('redis_maxmemory') ? `${maxMemoryDisplay.value}${maxMemoryDisplay.unit}` : '未配置'}</span></div>
                        <div className={styles.detailMetricRow}><span className={styles.detailMetricLabel}>内存碎片率</span><span className={styles.detailMetricValue}>{renderMetricValue('redis_mem_fragmentation_ratio', fragmentationDisplay.value)}</span></div>
                        <div
                          className={`${styles.fragmentationWarning} ${
                            fragmentationTone === 'danger'
                              ? styles.fragmentationWarningDanger
                              : fragmentationTone === 'warn'
                                ? styles.fragmentationWarningWarn
                                : styles.fragmentationWarningNormal
                          }`}
                        >
                          {fragmentationTone === 'danger'
                            ? '碎片率偏高，建议排查内存抖动与键淘汰。'
                            : fragmentationTone === 'warn'
                              ? '碎片率开始升高，需要结合内存使用率持续观察。'
                              : '当前碎片率平稳。'}
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className={`${styles.modeContent} ${styles.metricsMode}`}>
                  <div className={`${styles.panel} ${styles.fullPanel}`}>
                    <div className={styles.panelHeader}>
                      <div className={styles.panelHeading}>
                        <h3 className={styles.panelTitle}>
                          <TitleWithGuide styles={styles} title="监控指标全景" items={metricsOverviewGuide} className={styles.panelTitleWithGuide} />
                        </h3>
                      </div>
                    </div>
                    <MetricViews
                      key={`${monitorObjectId}-${instanceId}-${idValues.join('|')}`}
                      monitorObjectId={monitorObjectId}
                      monitorObjectName={monitorObjectName}
                      instanceId={String(instanceId)}
                      instanceName={instanceName}
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
