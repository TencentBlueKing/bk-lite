'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Empty } from 'antd';
import {
  DatabaseOutlined,
  StopOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import {
  StatCard,
  CollectionStatusCard,
  TitleWithGuide,
  DashboardPageHeader,
  DashboardInstanceCard,
  DashboardPanel,
  DetailPanel,
  TrendChartPanel,
  RingChartPanel,
  HorizontalBarPanel
} from '../../shared/widgets';
import { DetailMetricRow } from '../common/dashboard-components';
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
import { TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
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
  'redis_blocked_clients',
  // 字节速率(byteps):禁用服务端自动换算,避免与前端 formatMetricValue 双重换算
  'redis_total_net_input_bytes',
  'redis_total_net_output_bytes'
]);

const METRIC_QUERY_CONCURRENCY = 4;

// 详情行 sparkline 取指标语义色,与 KPI/趋势/异常信号条统一配色。
const metricColor = (name: string): string | undefined =>
  DASHBOARD_METRICS.find((m) => m.name === name)?.color;

const REDIS_METRIC_GROUPS = [
  {
    // Primary signals: capacity risk + cache efficiency — load first
    key: 'summary',
    names: [
      'redis_used_memory',
      'redis_maxmemory',
      'redis_memory_utilization',
      'redis_keyspace_hitrate',
      'redis_keyspace_hits_rate',
      'redis_keyspace_misses_rate',
      'redis_evicted_keys_rate',
      'redis_rejected_connections_rate',
      'redis_clients',
      'redis_blocked_clients'
    ]
  },
  {
    // Diagnostic / trend layer — load after primary cards are ready
    key: 'trends',
    names: [
      'redis_mem_fragmentation_ratio',
      'redis_instantaneous_ops_per_sec',
      'redis_total_commands_processed_rate',
      'redis_total_net_input_bytes_rate',
      'redis_total_net_output_bytes_rate',
      'redis_expired_keys_rate',
      'redis_uptime'
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
  const [, setLoading] = useState(true);
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
          ['redis_memory_utilization', 'redis_evicted_keys_rate', 'redis_keyspace_hitrate', 'redis_rejected_connections_rate'].includes(metric.name)
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

        if (!silent) {
          setPreviousSeries({});
        }

        previousMetricResultsPromise.then((previousResults) => {
          if (loadSeqRef.current !== loadSeq) return;
          setPreviousSeries(Object.fromEntries(previousResults));
        });

        const [summaryResults, collectionStatus] = await Promise.all([
          summaryResultsPromise,
          collectionStatusPromise
        ]);

        if (loadSeqRef.current !== loadSeq) return;

        setSeries((prev) => (silent ? { ...prev, ...Object.fromEntries(summaryResults) } : Object.fromEntries(summaryResults)));
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
  const netInputValue = getLatest('redis_total_net_input_bytes_rate');
  const netOutputValue = getLatest('redis_total_net_output_bytes_rate');
  const netInputDisplay = formatMetricValue(netInputValue, 'byteps');
  const netOutputDisplay = formatMetricValue(netOutputValue, 'byteps');

  const memoryCompare = maxMemoryValue > 0 ? getPeriodCompare(memoryUtilValue, getPreviousLatest('redis_memory_utilization')) : null;
  const evictedCompare = getPeriodCompare(evictedRateValue, getPreviousLatest('redis_evicted_keys_rate'));
  const hitRateCompare = getPeriodCompare(hitRateValue, getPreviousLatest('redis_keyspace_hitrate'));
  const rejectedCompare = getPeriodCompare(rejectedRateValue, getPreviousLatest('redis_rejected_connections_rate'));

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

  const cacheHitMissTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'redis_keyspace_hits_rate',
          label: '键命中频率',
          displayName: '键命中频率',
          data: metricMap.redis_keyspace_hits_rate?.viewData || []
        },
        {
          key: 'redis_keyspace_misses_rate',
          label: '键未命中频率',
          displayName: '键未命中频率',
          data: metricMap.redis_keyspace_misses_rate?.viewData || []
        }
      ]),
    [metricMap.redis_keyspace_hits_rate?.viewData, metricMap.redis_keyspace_misses_rate?.viewData]
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
  const evictedGuide = [
    { label: '键驱逐频率', detail: '因内存达到上限被主动淘汰的键频率，非零即说明内存容量不足，会直接导致缓存命中率下降。' },
    { label: '排查建议', detail: '结合内存使用率与碎片率判断：若使用率已高则需扩容或调整淘汰策略。' }
  ];
  const rejectedGuide = [
    { label: '连接拒绝频率', detail: '因达到 maxclients 限制被拒绝的连接请求频率，非零说明客户端整体压力已超上限。' },
    { label: '排查建议', detail: '若阻塞客户端数量同时升高，优先排查热点命令（热点导致）；否则说明是整体连接规模超限（资源饱和）。' }
  ];
  const hitGuide = [
    { label: '缓存命中率', detail: '表示键命中占总键访问的比例。' },
    { label: '关联判断', detail: '命中率降低时，应结合命中频率、未命中频率和内存使用率一起分析。' }
  ];
  const clientGuide = [
    { label: '客户端连接数', detail: '表示当前活跃的客户端连接总量。' },
    { label: '阻塞客户端诊断', detail: '阻塞数升高 + 拒绝频率高 → 热点命令导致排队；阻塞数低但拒绝频率高 → 整体连接规模超限（资源饱和）。' }
  ];
  const memoryTrendGuide = [
    { label: '内存压力趋势', detail: '同时展示已用内存与内存上限，判断实例是否逼近容量边界。碎片率详情见下方内存分布面板。' }
  ];
  const cacheHitMissTrendGuide = [
    { label: '命中/未命中趋势', detail: '同时展示键命中频率与未命中频率，通过两条曲线的比例直观判断缓存效率是否下降。' }
  ];
  const opsTrendGuide = [
    { label: '命令吞吐趋势', detail: '同时展示实时 OPS 和命令处理速率，判断 Redis 当前吞吐变化。' }
  ];
  const keyLifecycleGuide = [
    { label: '键生命周期与网络', detail: '展示过期键与驱逐键频率，以及网络入/出流量，判断缓存淘汰行为和请求压力。' }
  ];
  const metricsOverviewGuide = [
    { label: '监控指标全景', detail: '这里承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' }
  ];

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
            showTimeSelector={false}
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
            timeSelectorProps={{
              timeDefaultValue,
              onTimeChange,
              onFrequenceChange,
              onRefresh: () => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))
            }}
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
                      title={<TitleWithGuide styles={styles} title="实时 OPS" items={[{ label: '实时 OPS', detail: '每秒操作数（instantaneous_ops_per_sec），反映 Redis 当前吞吐。' }]} className={styles.statTitleWithGuide} />}
                      value={renderMetricValue('redis_instantaneous_ops_per_sec', opsDisplay.value)}
                      unit={hasMetricData('redis_instantaneous_ops_per_sec') ? opsDisplay.unit : ''}
                      icon={<DatabaseOutlined />}
                      iconStyle={{ background: 'rgba(39, 194, 116, 0.12)', color: '#27c274' }}
                      color="#27c274"
                      footer={<span>命令处理 {renderMetricValue('redis_total_commands_processed_rate', `${commandRateDisplay.value}${commandRateDisplay.unit}`)}</span>}
                      trendData={metricMap.redis_instantaneous_ops_per_sec?.viewData || []}
                      noDataType={getNoDataType('redis_instantaneous_ops_per_sec')}
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
                      title={<TitleWithGuide styles={styles} title="键驱逐频率" items={evictedGuide} className={styles.statTitleWithGuide} />}
                      value={renderMetricValue('redis_evicted_keys_rate', evictedDisplay.value)}
                      unit={hasMetricData('redis_evicted_keys_rate') ? evictedDisplay.unit : ''}
                      icon={<WarningOutlined />}
                      iconStyle={{ background: 'rgba(255, 77, 79, 0.12)', color: '#ff4d4f' }}
                      color="#ff4d4f"
                      footer={
                        <span>内存使用率 {maxMemoryValue > 0 && hasMetricData('redis_memory_utilization') ? `${memoryUtilDisplay.value}${memoryUtilDisplay.unit}` : '--'}</span>
                      }
                      compare={evictedCompare}
                      trendData={metricMap.redis_evicted_keys_rate?.viewData || []}
                      noDataType={getNoDataType('redis_evicted_keys_rate')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="连接拒绝频率" items={rejectedGuide} className={styles.statTitleWithGuide} />}
                      value={renderMetricValue('redis_rejected_connections_rate', rejectedDisplay.value)}
                      unit={hasMetricData('redis_rejected_connections_rate') ? rejectedDisplay.unit : ''}
                      icon={<StopOutlined />}
                      iconStyle={{ background: 'rgba(255, 77, 79, 0.12)', color: '#ff4d4f' }}
                      color="#ff4d4f"
                      footer={
                        <span>阻塞客户端 {renderMetricValue('redis_blocked_clients', blockedClientsDisplay.value)}</span>
                      }
                      compare={rejectedCompare}
                      trendData={metricMap.redis_rejected_connections_rate?.viewData || []}
                      noDataType={getNoDataType('redis_rejected_connections_rate')}
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
                      compareFavorableDirection="up"
                      trendData={metricMap.redis_keyspace_hitrate?.viewData || []}
                      noDataType={getNoDataType('redis_keyspace_hitrate')}
                    />
                  </div>

                  <div className={styles.mainTrendGrid}>
                    <TrendChartPanel
                      styles={styles}
                      className={styles.halfPanel}
                      title={<TitleWithGuide styles={styles} title="内存压力趋势" items={memoryTrendGuide} className={styles.panelTitleWithGuide} />}
                      subtitle="已用内存与上限"
                      guide={memoryTrendGuide}
                      legends={TREND_LEGENDS.memory}
                      data={memoryTrendData}
                      metric={buildMetricItem(metricMap.redis_used_memory || { ...DASHBOARD_METRICS[1], viewData: [], loadState: 'success' })}
                      unit="bytes"
                      seriesStyles={[
                        { color: TREND_LEGENDS.memory[0].color, unit: 'bytes' },
                        { color: TREND_LEGENDS.memory[1].color, strokeDasharray: '5 5', unit: 'bytes' }
                      ]}
                      onXRangeChange={onXRangeChange}
                    />

                    <TrendChartPanel
                      styles={styles}
                      className={styles.halfPanel}
                      title={<TitleWithGuide styles={styles} title="命中/未命中趋势" items={cacheHitMissTrendGuide} className={styles.panelTitleWithGuide} />}
                      subtitle="键命中与未命中频率"
                      guide={cacheHitMissTrendGuide}
                      legends={TREND_LEGENDS.cache}
                      data={cacheHitMissTrendData}
                      metric={buildMetricItem(metricMap.redis_keyspace_hits_rate || { ...DASHBOARD_METRICS[7], viewData: [], loadState: 'success' })}
                      unit="cps"
                      seriesStyles={[
                        { color: TREND_LEGENDS.cache[0].color, unit: 'cps' },
                        { color: TREND_LEGENDS.cache[1].color, unit: 'cps' }
                      ]}
                      onXRangeChange={onXRangeChange}
                    />

                    <TrendChartPanel
                      styles={styles}
                      className={styles.halfPanel}
                      title={<TitleWithGuide styles={styles} title="命令吞吐趋势" items={opsTrendGuide} className={styles.panelTitleWithGuide} />}
                      subtitle="OPS 与命令处理"
                      guide={opsTrendGuide}
                      legends={TREND_LEGENDS.ops}
                      data={opsTrendData}
                      metric={buildMetricItem(metricMap.redis_instantaneous_ops_per_sec || { ...DASHBOARD_METRICS[5], viewData: [], loadState: 'success' })}
                      unit="cps"
                      seriesStyles={[
                        { color: TREND_LEGENDS.ops[0].color, unit: 'cps' },
                        { color: TREND_LEGENDS.ops[1].color, unit: 'cps' }
                      ]}
                      onXRangeChange={onXRangeChange}
                    />
                  </div>

                  <div className={styles.detailGrid}>
                    <RingChartPanel
                      styles={styles}
                      className={styles.quarterPanel}
                      title={<TitleWithGuide styles={styles} title="内存占用分布" items={memoryGuide} className={styles.panelTitleWithGuide} />}
                      subtitle="已用、上限与碎片"
                      guide={memoryGuide}
                      isEmpty={!hasMetricData('redis_used_memory') && !hasMetricData('redis_memory_utilization')}
                      data={(() => {
                        const used = hasMetricData('redis_used_memory') ? usedMemoryValue : 0;
                        const max = hasMetricData('redis_maxmemory') && maxMemoryValue > 0 ? maxMemoryValue : used;
                        const free = Math.max(max - used, 0);
                        return [
                          { name: '已用', value: used, color: '#ff8a1f' },
                          { name: '剩余', value: free, color: '#e8f0fe' }
                        ];
                      })()}
                      centerValue={maxMemoryValue > 0 && hasMetricData('redis_memory_utilization') ? `${memoryUtilDisplay.value}%` : '--'}
                      centerCaption="使用率"
                      infoRows={[
                        {
                          name: '已用内存',
                          color: '#ff8a1f',
                          primary: renderMetricValue('redis_used_memory', `${usedMemoryDisplay.value}${usedMemoryDisplay.unit}`)
                        },
                        {
                          name: '内存上限',
                          color: '#e8f0fe',
                          primary: maxMemoryValue > 0 && hasMetricData('redis_maxmemory') ? `${maxMemoryDisplay.value}${maxMemoryDisplay.unit}` : '未配置'
                        },
                        {
                          name: '碎片率',
                          color: '#faad14',
                          primary: renderMetricValue('redis_mem_fragmentation_ratio', fragmentationDisplay.value)
                        }
                      ]}
                    />

                    <RingChartPanel
                      styles={styles}
                      className={styles.quarterPanel}
                      title={<TitleWithGuide styles={styles} title="命中分布" items={hitGuide} className={styles.panelTitleWithGuide} />}
                      subtitle="命中、未命中与命中率"
                      guide={hitGuide}
                      isEmpty={!hasMetricData('redis_keyspace_hits_rate') && !hasMetricData('redis_keyspace_misses_rate')}
                      data={[
                        { name: '命中', value: hasMetricData('redis_keyspace_hits_rate') ? hitsRateValue : 0, color: '#8a5cff' },
                        { name: '未命中', value: hasMetricData('redis_keyspace_misses_rate') ? missesRateValue : 0, color: '#ffccc7' }
                      ]}
                      centerValue={hasMetricData('redis_keyspace_hitrate') ? `${hitRateDisplay.value}%` : '--'}
                      centerCaption="命中率"
                      infoRows={[
                        {
                          name: '键命中频率',
                          color: '#8a5cff',
                          primary: renderMetricValue('redis_keyspace_hits_rate', `${hitsRateDisplay.value}${hitsRateDisplay.unit}`)
                        },
                        {
                          name: '键未命中频率',
                          color: '#ffccc7',
                          primary: renderMetricValue('redis_keyspace_misses_rate', `${missesRateDisplay.value}${missesRateDisplay.unit}`)
                        },
                        {
                          name: '命中率',
                          color: '#27c274',
                          primary: renderMetricValue('redis_keyspace_hitrate', `${hitRateDisplay.value}${hitRateDisplay.unit}`)
                        }
                      ]}
                    />

                    <HorizontalBarPanel
                      styles={styles}
                      className={styles.quarterPanel}
                      title={<TitleWithGuide styles={styles} title="客户端状态" items={clientGuide} className={styles.panelTitleWithGuide} />}
                      subtitle="连接、阻塞与拒绝"
                      guide={clientGuide}
                      items={(() => {
                        const normalClients = Math.max(clientsValue - blockedClientsValue, 0);
                        const maxVal = Math.max(clientsValue, 1);
                        return [
                          { label: '正常连接', value: normalClients, display: hasMetricData('redis_clients') ? normalClients.toFixed(0) : '--', color: '#2f6bff', max: maxVal, trend: metricMap.redis_clients?.viewData || [] },
                          { label: '阻塞客户端', value: blockedClientsValue, display: renderMetricValue('redis_blocked_clients', blockedClientsDisplay.value), color: '#fa8c16', max: maxVal, trend: metricMap.redis_blocked_clients?.viewData || [] },
                          { label: '连接拒绝频率', value: rejectedRateValue, display: renderMetricValue('redis_rejected_connections_rate', `${rejectedDisplay.value}${rejectedDisplay.unit}`), color: '#ff4d4f', max: Math.max(rejectedRateValue, clientsValue, 1), trend: metricMap.redis_rejected_connections_rate?.viewData || [] }
                        ];
                      })()}
                    />

                    <DetailPanel
                      styles={styles}
                      className={styles.quarterPanel}
                      title="键生命周期与网络"
                      subtitle="过期、驱逐与网络流量"
                      guide={keyLifecycleGuide}
                    >
                      <DetailMetricRow
                        styles={styles}
                        label="键过期频率"
                        value={renderMetricValue('redis_expired_keys_rate', `${expiredDisplay.value}${expiredDisplay.unit}`)}
                        viz={hasMetricData('redis_expired_keys_rate') ? 'spark' : 'none'}
                        trend={metricMap.redis_expired_keys_rate?.viewData || []}
                        color={metricColor('redis_expired_keys_rate')}
                      />
                      <DetailMetricRow
                        styles={styles}
                        label="键驱逐频率"
                        value={renderMetricValue('redis_evicted_keys_rate', `${evictedDisplay.value}${evictedDisplay.unit}`)}
                        viz={hasMetricData('redis_evicted_keys_rate') ? 'spark' : 'none'}
                        trend={metricMap.redis_evicted_keys_rate?.viewData || []}
                        tone={evictedRateValue > 0 ? 'error' : 'normal'}
                        color={metricColor('redis_evicted_keys_rate')}
                      />
                      <DetailMetricRow
                        styles={styles}
                        label="网络入流量"
                        value={renderMetricValue('redis_total_net_input_bytes_rate', `${netInputDisplay.value}${netInputDisplay.unit}`)}
                        viz={hasMetricData('redis_total_net_input_bytes_rate') ? 'spark' : 'none'}
                        trend={metricMap.redis_total_net_input_bytes_rate?.viewData || []}
                        color={metricColor('redis_total_net_input_bytes_rate')}
                      />
                      <DetailMetricRow
                        styles={styles}
                        label="网络出流量"
                        value={renderMetricValue('redis_total_net_output_bytes_rate', `${netOutputDisplay.value}${netOutputDisplay.unit}`)}
                        viz={hasMetricData('redis_total_net_output_bytes_rate') ? 'spark' : 'none'}
                        trend={metricMap.redis_total_net_output_bytes_rate?.viewData || []}
                        color={metricColor('redis_total_net_output_bytes_rate')}
                      />
                    </DetailPanel>
                  </div>
                </>
              ) : (
                <div className={`${styles.modeContent} ${styles.metricsMode}`}>
                  <DashboardPanel
                    styles={styles}
                    className={styles.fullPanel}
                    title="监控指标全景"
                    guide={metricsOverviewGuide}
                  >
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
                  </DashboardPanel>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
