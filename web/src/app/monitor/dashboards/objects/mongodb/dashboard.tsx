'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ClockCircleOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  NodeIndexOutlined,
  PauseCircleOutlined
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
  RingChartPanel
} from '../../shared/widgets';
import { DetailMetricRow } from '../common/dashboard-components';
import { formatDuration, countRestartsInRange } from '../common/simple-dashboard-core';
import {
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
  runWithConcurrency,
  formatMetricValue,
  useLoadSequence
} from '../../shared/utils';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import useMonitorApi from '@/app/monitor/api';
import { useTranslation } from '@/utils/i18n';
import { ChartData, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import {
  DASHBOARD_METRICS,
  MONGODB_COLLECTION_STATUS_QUERY,
  TREND_LEGENDS
} from './config';
import { MetricSeries, MetricUnit, MongoMetricConfig } from './types';
import styles from './index.module.scss';

interface InstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
  interval?: number;
}

const MEBIBYTE = 1024 * 1024;

const METRIC_QUERY_CONCURRENCY = 4;

// 详情行 sparkline 取指标语义色,与 KPI/趋势统一配色。
const metricColor = (name: string): string | undefined =>
  DASHBOARD_METRICS.find((m) => m.name === name)?.color;

const MONGODB_METRIC_GROUPS = [
  {
    key: 'summary',
    names: [
      'mongodb_uptime_ns',
      'mongodb_connections_current',
      'mongodb_connections_available',
      'mongodb_open_connections',
      'mongodb_commands_rate',
      'mongodb_queries_rate',
      'mongodb_write_ops_rate',
      'mongodb_latency_reads_avg',
      'mongodb_latency_commands_avg',
      'mongodb_page_faults_rate',
      'mongodb_active_reads',
      'mongodb_active_writes',
      'mongodb_queued_reads',
      'mongodb_queued_writes',
      'mongodb_wtcache_usage_ratio'
    ]
  },
  {
    key: 'trends',
    names: [
      'mongodb_resident_megabytes',
      'mongodb_vsize_megabytes',
      'mongodb_wtcache_current_bytes',
      'mongodb_wtcache_max_bytes_configured',
      'mongodb_wtcache_tracked_dirty_bytes',
      'mongodb_net_in_bytes_count_rate',
      'mongodb_net_out_bytes_count_rate',
      'mongodb_cursor_timed_out_count',
      'mongodb_assert_user'
    ]
  }
];
const multiplyChartDataValues = (data: ChartData[], factor: number) =>
  data.map((point) => {
    const next: ChartData = { ...point };
    Object.entries(point).forEach(([key, current]) => {
      if (key.startsWith('value') && typeof current === 'number' && Number.isFinite(current)) {
        next[key] = current * factor;
      }
    });
    return next;
  });

export default function MongoDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const [, setLoading] = useState(true);
  const [displayMode, setDisplayMode] = useState<'dashboard' | 'metrics'>('dashboard');
  const [timeValues, setTimeValues] = useState<TimeValuesProps>({ timeRange: [], originValue: 15 });
  const [timeDefaultValue, setTimeDefaultValue] = useState<TimeSelectorDefaultValue>({
    selectValue: 15,
    rangePickerVaule: null
  });
  const [frequence, setFrequence] = useState<number>(0);
  const [series, setSeries] = useState<Record<string, MetricSeries>>({});
  const [previousSeries, setPreviousSeries] = useState<Record<string, MetricSeries>>({});
  const [collectionStatusMetric, setCollectionStatusMetric] = useState<MetricSeries | null>(null);
  const [instanceOptions, setInstanceOptions] = useState<InstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);
  const loadSequence = useLoadSequence();

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || 'Mongodb';
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || 'MongoDB';
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
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || 'MongoDB';
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
            instanceIdValues:
              Array.isArray(item.instance_id_values) && item.instance_id_values.length ? item.instance_id_values : [value],
            searchTokens: buildInstanceSearchTokens(item, label),
            interval: Number(item.interval) || undefined
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
  const currentInstanceInterval = currentInstanceOption?.interval;
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
  const instanceSelectValue =
    currentInstanceOption?.value || (hasReadableInstanceName && instanceId ? String(instanceId) : undefined);

  const loadMetricGroup = async (metricNames: readonly string[]) => {
    const metrics = metricNames
      .map((name) => DASHBOARD_METRICS.find((m) => m.name === name))
      .filter((m): m is MongoMetricConfig => Boolean(m));
    return runWithConcurrency(
      metrics,
      METRIC_QUERY_CONCURRENCY,
      async (metric) =>
        getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues, undefined, false, currentInstanceInterval))
          .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
          .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
    );
  };

  const loadMetrics = async (silent = false) => {
    const loadSeq = loadSequence.begin();

    if (!silent) setLoading(true);
    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = DASHBOARD_METRICS.filter((metric) =>
          ['mongodb_connections_current'].includes(metric.name)
        );

        const summaryResultsPromise = loadMetricGroup(MONGODB_METRIC_GROUPS[0].names);

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(
          buildSearchParams(MONGODB_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues, undefined, false, currentInstanceInterval)
        )
          .then((result) =>
            toMetricSeries<MongoMetricConfig>(
              {
                name: 'mongodb_collection_status',
                display_name: '采集状态',
                description: 'MongoDB 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts' as MetricUnit,
                query: MONGODB_COLLECTION_STATUS_QUERY,
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
                name: 'mongodb_collection_status',
                display_name: '采集状态',
                description: 'MongoDB 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts' as MetricUnit,
                query: MONGODB_COLLECTION_STATUS_QUERY,
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
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues, undefined, undefined, currentInstanceInterval))
                .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
                .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
          : Promise.resolve([] as Array<readonly [string, MetricSeries]>);

        if (!silent) {
          setPreviousSeries({});
        }

        previousMetricResultsPromise.then((previousResults) => {
          if (!loadSequence.isCurrent(loadSeq)) return;
          setPreviousSeries(Object.fromEntries(previousResults));
        });

        const [summaryResults, collectionStatus] = await Promise.all([
          summaryResultsPromise,
          collectionStatusPromise
        ]);

        if (!loadSequence.isCurrent(loadSeq)) return;

        setSeries((prev) => (silent ? { ...prev, ...Object.fromEntries(summaryResults) } : Object.fromEntries(summaryResults)));
        setCollectionStatusMetric(collectionStatus);

        if (!silent) setLoading(false);

        MONGODB_METRIC_GROUPS.slice(1).forEach((group) => {
          loadMetricGroup(group.names).then((results) => {
            if (!loadSequence.isCurrent(loadSeq)) return;
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
      if (loadSequence.isCurrent(loadSeq) && !silent) setLoading(false);
    }
  };

  useEffect(() => {
    if (isDashboardMode) {
      loadMetrics();
      return;
    }
    setLoading(false);
  }, [currentInstanceInterval, instanceId, idValuesKey, timeValues, isDashboardMode]);

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
  }, [currentInstanceInterval, frequence, timeValues, instanceId, idValuesKey, isDashboardMode]);

  const metricMap = useMemo(() => series, [series]);
  const previousMetricMap = useMemo(() => previousSeries, [previousSeries]);
  const getLatest = (name: string) => getLatestChartValue(metricMap[name]?.viewData || []);
  const hasMetricData = (name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  };
  const renderMetricValue = (name: string, value: string) => (hasMetricData(name) ? value : '--');

  const uptimeNs = getLatest('mongodb_uptime_ns');
  const currentConnections = getLatest('mongodb_connections_current');
  const availableConnections = getLatest('mongodb_connections_available');
  const openConnections = getLatest('mongodb_open_connections');
  const commandsRate = getLatest('mongodb_commands_rate');
  const queriesRate = getLatest('mongodb_queries_rate');
  const writesRate = getLatest('mongodb_write_ops_rate');
  const readLatency = getLatest('mongodb_latency_reads_avg');
  const pageFaults = getLatest('mongodb_page_faults_rate');
  const queuedReads = getLatest('mongodb_queued_reads');
  const queuedWrites = getLatest('mongodb_queued_writes');
  const activeReads = getLatest('mongodb_active_reads');
  const activeWrites = getLatest('mongodb_active_writes');
  const residentMemory = getLatest('mongodb_resident_megabytes');
  const virtualMemory = getLatest('mongodb_vsize_megabytes');
  const cacheCurrent = getLatest('mongodb_wtcache_current_bytes');
  const cacheMax = getLatest('mongodb_wtcache_max_bytes_configured');
  const cacheDirty = getLatest('mongodb_wtcache_tracked_dirty_bytes');
  const cacheUsageRatio = getLatest('mongodb_wtcache_usage_ratio');
  const netIn = getLatest('mongodb_net_in_bytes_count_rate');
  const netOut = getLatest('mongodb_net_out_bytes_count_rate');
  const cursorTimedOut = getLatest('mongodb_cursor_timed_out_count');
  const userAssert = getLatest('mongodb_assert_user');

  const collectionStatus = getCollectionStatus(collectionStatusMetric, 'MongoDB');
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric?.loadState, collectionStatusMetric?.viewData);

  const connectionsDisplay = formatMetricValue(currentConnections, 'counts');
  const commandsDisplay = formatMetricValue(commandsRate, 'cps');
  const queriesDisplay = formatMetricValue(queriesRate, 'cps');
  const writesDisplay = formatMetricValue(writesRate, 'cps');
  const readLatencyDisplay = formatMetricValue(readLatency, 'ns');
  const uptimeDisplay = formatDuration(uptimeNs / 1e9);
  const uptimeStartedAt = hasMetricData('mongodb_uptime_ns') && uptimeNs >= 0
    ? dayjs().subtract(Math.floor(uptimeNs / 1e9), 'second').format('YYYY-MM-DD HH:mm:ss')
    : '--';
  // 运行时长卡统一样式:不画折线,只判断所选时间范围内是否发生重启。
  const uptimeStatus = !hasMetricData('mongodb_uptime_ns')
    ? { label: '状态未知', suffix: 'Empty' as const }
    : countRestartsInRange(metricMap.mongodb_uptime_ns?.viewData || []) > 0
      ? { label: '期间有重启', suffix: 'Warning' as const }
      : { label: '运行正常', suffix: 'Success' as const };
  const pageFaultDisplay = formatMetricValue(pageFaults, 'cps');
  const cacheUsageDisplay = formatMetricValue(cacheUsageRatio, 'percent');
  const cacheCurrentDisplay = formatMetricValue(cacheCurrent, 'bytes');
  const cacheMaxDisplay = formatMetricValue(cacheMax, 'bytes');
  const cacheDirtyDisplay = formatMetricValue(cacheDirty, 'bytes');
  const residentDisplay = formatMetricValue(residentMemory, 'mebibytes');
  const virtualDisplay = formatMetricValue(virtualMemory, 'mebibytes');
  const netInDisplay = formatMetricValue(netIn, 'byteps');
  const netOutDisplay = formatMetricValue(netOut, 'byteps');

  const connectionCompare = getPeriodCompare(currentConnections, getLatestChartValue(previousMetricMap.mongodb_connections_current?.viewData || []));

  const buildThroughputSeries = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_commands_rate', label: '命令吞吐', displayName: '命令吞吐', data: metricMap.mongodb_commands_rate?.viewData || [] },
        { key: 'mongodb_queries_rate', label: '查询吞吐', displayName: '查询吞吐', data: metricMap.mongodb_queries_rate?.viewData || [] },
        { key: 'mongodb_write_ops_rate', label: '写入吞吐', displayName: '写入吞吐', data: metricMap.mongodb_write_ops_rate?.viewData || [] }
      ]),
    [metricMap.mongodb_commands_rate?.viewData, metricMap.mongodb_queries_rate?.viewData, metricMap.mongodb_write_ops_rate?.viewData]
  );

  const latencyTrendData = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_latency_reads_avg', label: '读延迟', displayName: '读延迟', data: metricMap.mongodb_latency_reads_avg?.viewData || [] },
        { key: 'mongodb_latency_commands_avg', label: '命令延迟', displayName: '命令延迟', data: metricMap.mongodb_latency_commands_avg?.viewData || [] }
      ]),
    [metricMap.mongodb_latency_reads_avg?.viewData, metricMap.mongodb_latency_commands_avg?.viewData]
  );

  const queueTrendData = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_active_reads', label: '活跃读', displayName: '活跃读', data: metricMap.mongodb_active_reads?.viewData || [] },
        { key: 'mongodb_active_writes', label: '活跃写', displayName: '活跃写', data: metricMap.mongodb_active_writes?.viewData || [] },
        { key: 'mongodb_queued_reads', label: '排队读', displayName: '排队读', data: metricMap.mongodb_queued_reads?.viewData || [] },
        { key: 'mongodb_queued_writes', label: '排队写', displayName: '排队写', data: metricMap.mongodb_queued_writes?.viewData || [] }
      ]),
    [
      metricMap.mongodb_active_reads?.viewData,
      metricMap.mongodb_active_writes?.viewData,
      metricMap.mongodb_queued_reads?.viewData,
      metricMap.mongodb_queued_writes?.viewData
    ]
  );

  const cacheTrendData = useMemo(
    () =>
      mergeChartSeries([
        { key: 'mongodb_wtcache_current_bytes', label: '缓存已用', displayName: '缓存已用', data: metricMap.mongodb_wtcache_current_bytes?.viewData || [] },
        { key: 'mongodb_wtcache_max_bytes_configured', label: '缓存上限', displayName: '缓存上限', data: metricMap.mongodb_wtcache_max_bytes_configured?.viewData || [] }
      ]),
    [metricMap.mongodb_wtcache_current_bytes?.viewData, metricMap.mongodb_wtcache_max_bytes_configured?.viewData]
  );

  const memoryTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mongodb_resident_megabytes',
          label: '常驻内存',
          displayName: '常驻内存',
          data: multiplyChartDataValues(metricMap.mongodb_resident_megabytes?.viewData || [], MEBIBYTE)
        },
        {
          key: 'mongodb_vsize_megabytes',
          label: '虚拟内存',
          displayName: '虚拟内存',
          data: multiplyChartDataValues(metricMap.mongodb_vsize_megabytes?.viewData || [], MEBIBYTE)
        }
      ]),
    [metricMap.mongodb_resident_megabytes?.viewData, metricMap.mongodb_vsize_megabytes?.viewData]
  );


  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : 'MongoDB 监控仪表盘';
  const instanceMetaItems = [
    <span key="object-name" className={styles.instanceMetaInline}>{objectDisplayText}</span>,
    <span key="engine" className={styles.instanceMetaInline}>引擎: WiredTiger</span>,
    <span key="timezone" className={styles.instanceMetaInline}>时区: Asia/Shanghai</span>
  ];

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({ timeRange: val, originValue });
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    if (!arr?.[0] || !arr?.[1]) return;
    const start = dayjs(arr[0]).valueOf();
    const end = dayjs(arr[1]).valueOf();
    if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) return;
    setTimeDefaultValue((prev) => ({ ...prev, rangePickerVaule: arr, selectValue: 0 }));
    setTimeValues({ timeRange: [start, end], originValue: 0 });
  };

  const onFrequenceChange = (val: number) => setFrequence(val);
  const goBack = () => router.push('/monitor/view');

  const onInstanceChange = (value: string) => {
    const target = instanceOptions.find((item) => item.value === value);
    const params = new URLSearchParams(searchParams.toString());
    params.set('instance_id', value);
    params.set('instance_name', String(target?.label || value));
    params.set('instance_id_values', (target?.instanceIdValues || [value]).join(','));
    router.push(`/monitor/view/dashboard/mongodb?${params.toString()}`);
  };

  const getNoDataType = (...metricNames: string[]): 'empty' | 'error' => {
    if (metricNames.includes('mongodb_collection_status')) {
      return collectionStatusMetric?.loadState === 'error' ? 'error' : 'empty';
    }
    const targets = metricNames.map((name) => metricMap[name]).filter(Boolean);
    return targets.length > 0 && targets.every((metric) => metric?.loadState === 'error') ? 'error' : 'empty';
  };

  const queuedReadsGuide = [
    { label: '排队读操作', detail: '等待执行的读操作数量。此值非零时表明读并发已超出处理能力，需关注锁等待与工作集匹配度。' },
    { label: '关联判断', detail: '结合排队写、命令延迟和缺页频率，共同判断是否存在资源争用瓶颈。' }
  ];
  const queuedWritesGuide = [
    { label: '排队写操作', detail: '等待执行的写操作数量。此值升高时通常伴随写延迟上升，需排查写入锁竞争。' },
    { label: '关联判断', detail: '结合排队读、活跃写和命令延迟，判断写入是否成为瓶颈。' }
  ];
  const pageFaultGuide = [
    { label: '缺页频率', detail: '每秒发生缺页中断的速率。值升高通常意味着工作集超出常驻内存，磁盘 I/O 介入频繁。' },
    { label: '关联判断', detail: '结合常驻内存、WiredTiger 缓存使用率和排队读写，判断内存工作集是否不匹配。' }
  ];
  const connectionGuide = [
    { label: '当前连接数', detail: '表示当前仍在使用中的客户端连接总量。' },
    { label: '关联判断', detail: '如果当前连接与打开连接同时升高，需要结合排队读写和延迟继续判断是否拥塞。' }
  ];
  const throughputGuide = [
    { label: '命令吞吐', detail: '表示 MongoDB 每秒处理的整体命令速率。' },
    { label: '关联判断', detail: '吞吐抬升时，需要结合缓存使用率、活跃读写和网络流量一起分析来源。' }
  ];
  const latencyTrendGuide = [
    { label: '延迟趋势', detail: '同时展示读延迟和命令延迟，判断响应速度变化与潜在瓶颈。单位：自动换算（ns/µs/ms/s）。' }
  ];
  const queueTrendGuide = [
    { label: '读写队列趋势', detail: '同时展示活跃读写和排队读写，用于判断当前负载是否已开始堆积。单位：个。' }
  ];
  const throughputTrendGuide = [
    { label: '吞吐趋势', detail: '同时展示命令吞吐、查询吞吐和写入吞吐，判断当前工作负载类型与变化节奏。单位：次/秒。' }
  ];
  const cacheTrendGuide = [
    { label: 'WiredTiger 缓存趋势', detail: '展示 WiredTiger 缓存已用量与配置上限，判断缓存是否趋于饱和。单位：自动换算（B/KB/MB/GB）。' }
  ];
  const memoryTrendGuide = [
    { label: '进程内存趋势', detail: '展示常驻内存和虚拟内存，判断 MongoDB 进程内存使用与工作集变化。单位：自动换算（B/KB/MB/GB）。' }
  ];
  const cacheGuide = [
    { label: '缓存使用率', detail: '表示 WiredTiger 当前已用缓存占配置上限的比例。' },
    { label: '搭配指标', detail: '应同时结合脏数据、常驻内存和缺页频率一起判断缓存是否成为瓶颈。' }
  ];
  const memoryDetailGuide = [
    { label: '进程内存', detail: '展示常驻内存和虚拟内存，用于判断 MongoDB 进程的实际内存使用情况。' },
    { label: '缺页参考', detail: '缺页频率升高时，对照常驻内存判断工作集是否超出物理内存。' }
  ];
  const networkDetailGuide = [
    { label: '网络与异常', detail: '展示网络流量、游标超时和用户断言，用于判断响应层异常。' }
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
            instanceName={resolvedInstanceName}
            metaItems={instanceMetaItems}
            icon={<DatabaseOutlined />}
            iconClassName={styles.mongoInstanceIcon}
            selectorValue={instanceSelectValue}
            selectorLoading={instanceLoading}
            selectorOptions={instanceSelectOptions}
            onInstanceChange={onInstanceChange}
            selectorPlaceholder={resolvedInstanceName !== '--' ? resolvedInstanceName : '选择实例'}
            selectorTitle={currentInstanceOption?.label || normalizedInstanceName || resolvedInstanceName}
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
          {displayMode === 'dashboard' ? (
            <>
              {/* 分区 1 · 健康概览：采集状态 + 关键 KPI */}
              <div className={styles.sectionLabel}>健康概览</div>
              <div className={styles.primaryGrid}>
                <CollectionStatusCard styles={styles} status={collectionStatus} timeline={collectionStatusTimeline} />
                <StatCard
                  styles={styles}
                  title={<TitleWithGuide styles={styles} title="运行时长" items={[{ label: '运行时长', detail: 'MongoDB 实例自上次启动后的持续运行时间，反映服务稳定性；期间发生重启会重新计时。' }]} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_uptime_ns', uptimeDisplay)}
                  unit=""
                  icon={<ClockCircleOutlined />}
                  iconStyle={{ background: 'rgba(91, 143, 249, 0.12)', color: '#5b8ff9' }}
                  color="#5b8ff9"
                  footer={<span>启动 {uptimeStartedAt}</span>}
                  hideTrend
                  className={styles.statCardRelaxed}
                  bodyClassName={styles.statBodyRelaxed}
                  extra={
                    <div className={`${styles.uptimeStatus} ${styles[`uptimeStatus${uptimeStatus.suffix}`]}`}>
                      <span className={styles.uptimeStatusDot} />
                      <div className={styles.uptimeStatusMainWrap}>
                        <span className={styles.uptimeStatusMain}>{uptimeStatus.label}</span>
                      </div>
                    </div>
                  }
                  noDataType={getNoDataType('mongodb_uptime_ns')}
                />
                <StatCard
                  styles={styles}
                  title={<TitleWithGuide styles={styles} title="排队读" items={queuedReadsGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_queued_reads', formatMetricValue(queuedReads, 'counts').value)}
                  unit=""
                  icon={<PauseCircleOutlined />}
                  iconStyle={{ background: 'rgba(91, 143, 249, 0.12)', color: '#5b8ff9' }}
                  color="#5b8ff9"
                  footer={
                    <>
                      <span>活跃读 {renderMetricValue('mongodb_active_reads', formatMetricValue(activeReads, 'counts').value)}</span>
                      <span>读延迟 {renderMetricValue('mongodb_latency_reads_avg', `${readLatencyDisplay.value}${readLatencyDisplay.unit}`)}</span>
                    </>
                  }
                  trendData={metricMap.mongodb_queued_reads?.viewData || []}
                  noDataType={getNoDataType('mongodb_queued_reads')}
                />
                <StatCard
                  styles={styles}
                  title={<TitleWithGuide styles={styles} title="排队写" items={queuedWritesGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_queued_writes', formatMetricValue(queuedWrites, 'counts').value)}
                  unit=""
                  icon={<PauseCircleOutlined />}
                  iconStyle={{ background: 'rgba(255, 159, 67, 0.12)', color: '#ff9f43' }}
                  color="#ff9f43"
                  footer={
                    <>
                      <span>活跃写 {renderMetricValue('mongodb_active_writes', formatMetricValue(activeWrites, 'counts').value)}</span>
                    </>
                  }
                  trendData={metricMap.mongodb_queued_writes?.viewData || []}
                  noDataType={getNoDataType('mongodb_queued_writes')}
                />
                <StatCard
                  styles={styles}
                  title={<TitleWithGuide styles={styles} title="缺页频率" items={pageFaultGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_page_faults_rate', pageFaultDisplay.value)}
                  unit={hasMetricData('mongodb_page_faults_rate') ? pageFaultDisplay.unit : ''}
                  icon={<ExclamationCircleOutlined />}
                  iconStyle={{ background: 'rgba(255, 77, 79, 0.10)', color: '#ff4d4f' }}
                  color="#ff4d4f"
                  footer={
                    <>
                      <span>常驻内存 {renderMetricValue('mongodb_resident_megabytes', `${residentDisplay.value}${residentDisplay.unit}`)}</span>
                    </>
                  }
                  trendData={metricMap.mongodb_page_faults_rate?.viewData || []}
                  noDataType={getNoDataType('mongodb_page_faults_rate')}
                />
                <StatCard
                  styles={styles}
                  title={<TitleWithGuide styles={styles} title="当前连接数" items={connectionGuide} className={styles.statTitleWithGuide} />}
                  value={renderMetricValue('mongodb_connections_current', connectionsDisplay.value)}
                  unit=""
                  icon={<NodeIndexOutlined />}
                  iconStyle={{ background: 'rgba(47, 107, 255, 0.12)', color: '#2f6bff' }}
                  color="#2f6bff"
                  footer={
                    <>
                      <span>打开 {renderMetricValue('mongodb_open_connections', formatMetricValue(openConnections, 'counts').value)}</span>
                      <span>可用 {renderMetricValue('mongodb_connections_available', formatMetricValue(availableConnections, 'counts').value)}</span>
                    </>
                  }
                  compare={connectionCompare}
                  trendData={metricMap.mongodb_connections_current?.viewData || []}
                  noDataType={getNoDataType('mongodb_connections_current')}
                />
              </div>

              {/* 分区 2 · 性能与队列：延迟 / 队列 / 吞吐趋势 */}
              <div className={styles.sectionLabel}>性能与队列</div>
              <div className={styles.mainTrendGrid}>
                <TrendChartPanel
                  styles={styles}
                  className={styles.halfPanel}
                  title={<TitleWithGuide styles={styles} title="延迟趋势" items={latencyTrendGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="读延迟与命令延迟变化"
                  legends={TREND_LEGENDS.latency}
                  data={latencyTrendData}
                  metric={buildMetricItem(metricMap.mongodb_latency_reads_avg || { ...DASHBOARD_METRICS[7], viewData: [], loadState: 'success' })}
                  unit="ns"
                  seriesStyles={[
                    { color: TREND_LEGENDS.latency[0].color, unit: 'ns' },
                    { color: TREND_LEGENDS.latency[1].color, unit: 'ns' }
                  ]}
                  onXRangeChange={onXRangeChange}
                />

                <TrendChartPanel
                  styles={styles}
                  className={styles.halfPanel}
                  title={<TitleWithGuide styles={styles} title="读写队列趋势" items={queueTrendGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="活跃读写与排队读写"
                  legends={TREND_LEGENDS.queue}
                  data={queueTrendData}
                  metric={buildMetricItem(metricMap.mongodb_active_reads || { ...DASHBOARD_METRICS[10], viewData: [], loadState: 'success' })}
                  unit="counts"
                  seriesStyles={TREND_LEGENDS.queue.map((item) => ({ color: item.color, unit: 'counts' }))}
                  onXRangeChange={onXRangeChange}
                />

                <TrendChartPanel
                  styles={styles}
                  className={styles.halfPanel}
                  title={<TitleWithGuide styles={styles} title="吞吐趋势" items={throughputTrendGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="命令、查询与写入变化"
                  legends={TREND_LEGENDS.throughput}
                  data={buildThroughputSeries}
                  metric={buildMetricItem(metricMap.mongodb_commands_rate || { ...DASHBOARD_METRICS[4], viewData: [], loadState: 'success' })}
                  unit="cps"
                  seriesStyles={TREND_LEGENDS.throughput.map((item) => ({ color: item.color, unit: 'cps' }))}
                  onXRangeChange={onXRangeChange}
                />
              </div>

              {/* 分区 3 · 缓存与内存：WiredTiger 缓存 + 进程内存趋势 */}
              <div className={styles.sectionLabel}>缓存与内存</div>
              <div className={styles.detailGrid}>
                <TrendChartPanel
                  styles={styles}
                  className={styles.halfWidePanel}
                  title={<TitleWithGuide styles={styles} title="WiredTiger 缓存趋势" items={cacheTrendGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="缓存已用与配置上限"
                  legends={TREND_LEGENDS.cache}
                  data={cacheTrendData}
                  metric={buildMetricItem(metricMap.mongodb_wtcache_current_bytes || { ...DASHBOARD_METRICS[17], viewData: [], loadState: 'success' })}
                  unit="bytes"
                  seriesStyles={[
                    { color: TREND_LEGENDS.cache[0].color, unit: 'bytes' },
                    { color: TREND_LEGENDS.cache[1].color, strokeDasharray: '5 5', unit: 'bytes' }
                  ]}
                  onXRangeChange={onXRangeChange}
                />

                <TrendChartPanel
                  styles={styles}
                  className={styles.halfWidePanel}
                  title={<TitleWithGuide styles={styles} title="进程内存趋势" items={memoryTrendGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="常驻内存与虚拟内存"
                  legends={TREND_LEGENDS.memory}
                  data={memoryTrendData}
                  metric={buildMetricItem(metricMap.mongodb_resident_megabytes || { ...DASHBOARD_METRICS[14], viewData: [], loadState: 'success' })}
                  unit="bytes"
                  seriesStyles={[
                    { color: TREND_LEGENDS.memory[0].color, unit: 'bytes' },
                    { color: TREND_LEGENDS.memory[1].color, unit: 'bytes' }
                  ]}
                  onXRangeChange={onXRangeChange}
                />
              </div>

              {/* 分区 4 · 诊断与明细：缓存/操作分布 + 内存/网络明细 */}
              <div className={styles.sectionLabel}>诊断与明细</div>
              <div className={styles.detailGrid}>
                <RingChartPanel
                  styles={styles}
                  className={styles.quarterPanel}
                  title={<TitleWithGuide styles={styles} title="WiredTiger 缓存" items={cacheGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="缓存占用与脏数据分布"
                  isEmpty={!hasMetricData('mongodb_wtcache_current_bytes') && !hasMetricData('mongodb_wtcache_usage_ratio')}
                  data={(() => {
                    const used = hasMetricData('mongodb_wtcache_current_bytes') ? cacheCurrent : 0;
                    const dirty = hasMetricData('mongodb_wtcache_tracked_dirty_bytes') ? cacheDirty : 0;
                    const max = hasMetricData('mongodb_wtcache_max_bytes_configured') && cacheMax > 0 ? cacheMax : used;
                    const free = Math.max(max - used, 0);
                    return [
                      { name: '已用', value: used - dirty, color: '#2f6bff' },
                      { name: '脏数据', value: dirty, color: '#fa8c16' },
                      { name: '空闲', value: free, color: '#e8f0fe' }
                    ];
                  })()}
                  centerValue={hasMetricData('mongodb_wtcache_usage_ratio') ? `${cacheUsageDisplay.value}%` : '--'}
                  centerCaption="缓存使用率"
                  infoRows={[
                    { name: '缓存已用', color: '#2f6bff', primary: renderMetricValue('mongodb_wtcache_current_bytes', `${cacheCurrentDisplay.value}${cacheCurrentDisplay.unit}`) },
                    { name: '脏数据', color: '#fa8c16', primary: renderMetricValue('mongodb_wtcache_tracked_dirty_bytes', `${cacheDirtyDisplay.value}${cacheDirtyDisplay.unit}`) },
                    { name: '缓存上限', color: '#e8f0fe', primary: renderMetricValue('mongodb_wtcache_max_bytes_configured', `${cacheMaxDisplay.value}${cacheMaxDisplay.unit}`) }
                  ]}
                />

                <RingChartPanel
                  styles={styles}
                  className={styles.quarterPanel}
                  title={<TitleWithGuide styles={styles} title="操作类型分布" items={throughputGuide} className={styles.panelTitleWithGuide} />}
                  subtitle="命令、查询与写入占比"
                  isEmpty={!hasMetricData('mongodb_commands_rate') && !hasMetricData('mongodb_queries_rate') && !hasMetricData('mongodb_write_ops_rate')}
                  data={[
                    { name: '命令', value: hasMetricData('mongodb_commands_rate') ? commandsRate : 0, color: '#27c274' },
                    { name: '查询', value: hasMetricData('mongodb_queries_rate') ? queriesRate : 0, color: '#5b8ff9' },
                    { name: '写入', value: hasMetricData('mongodb_write_ops_rate') ? writesRate : 0, color: '#ff9f43' }
                  ]}
                  centerValue={hasMetricData('mongodb_commands_rate') ? formatMetricValue(commandsRate + queriesRate + writesRate, 'cps').value : '--'}
                  centerCaption="总吞吐"
                  infoRows={[
                    { name: '命令', color: '#27c274', primary: renderMetricValue('mongodb_commands_rate', `${commandsDisplay.value}${commandsDisplay.unit}`) },
                    { name: '查询', color: '#5b8ff9', primary: renderMetricValue('mongodb_queries_rate', `${queriesDisplay.value}${queriesDisplay.unit}`) },
                    { name: '写入', color: '#ff9f43', primary: renderMetricValue('mongodb_write_ops_rate', `${writesDisplay.value}${writesDisplay.unit}`) }
                  ]}
                />

                <DetailPanel
                  styles={styles}
                  className={styles.quarterPanel}
                  title="内存与缺页"
                  subtitle="工作集与进程内存匹配"
                  guide={memoryDetailGuide}
                >
                  <DetailMetricRow styles={styles} label="常驻内存" value={renderMetricValue('mongodb_resident_megabytes', `${residentDisplay.value}${residentDisplay.unit}`)} viz={hasMetricData('mongodb_resident_megabytes') ? 'spark' : 'none'} trend={metricMap.mongodb_resident_megabytes?.viewData || []} color={metricColor('mongodb_resident_megabytes')} />
                  <DetailMetricRow styles={styles} label="虚拟内存" value={renderMetricValue('mongodb_vsize_megabytes', `${virtualDisplay.value}${virtualDisplay.unit}`)} viz={hasMetricData('mongodb_vsize_megabytes') ? 'spark' : 'none'} trend={metricMap.mongodb_vsize_megabytes?.viewData || []} color={metricColor('mongodb_vsize_megabytes')} />
                  <DetailMetricRow styles={styles} label="缺页频率" value={renderMetricValue('mongodb_page_faults_rate', `${pageFaultDisplay.value}${pageFaultDisplay.unit}`)} viz={hasMetricData('mongodb_page_faults_rate') ? 'spark' : 'none'} trend={metricMap.mongodb_page_faults_rate?.viewData || []} color={metricColor('mongodb_page_faults_rate')} />
                </DetailPanel>

                <DetailPanel
                  styles={styles}
                  className={styles.quarterPanel}
                  title="网络与异常"
                  subtitle="结果返回与异常信号"
                  guide={networkDetailGuide}
                >
                  <DetailMetricRow styles={styles} label="入流量" value={renderMetricValue('mongodb_net_in_bytes_count_rate', `${netInDisplay.value}${netInDisplay.unit}`)} viz={hasMetricData('mongodb_net_in_bytes_count_rate') ? 'spark' : 'none'} trend={metricMap.mongodb_net_in_bytes_count_rate?.viewData || []} color={metricColor('mongodb_net_in_bytes_count_rate')} />
                  <DetailMetricRow styles={styles} label="出流量" value={renderMetricValue('mongodb_net_out_bytes_count_rate', `${netOutDisplay.value}${netOutDisplay.unit}`)} viz={hasMetricData('mongodb_net_out_bytes_count_rate') ? 'spark' : 'none'} trend={metricMap.mongodb_net_out_bytes_count_rate?.viewData || []} color={metricColor('mongodb_net_out_bytes_count_rate')} />
                  <DetailMetricRow styles={styles} label="游标超时数" guide={[{ label: '游标超时数', detail: '空闲超时被服务端回收的查询游标累计数;偏高常因结果未及时遍历完。' }]} value={renderMetricValue('mongodb_cursor_timed_out_count', formatMetricValue(cursorTimedOut, 'counts').value)} viz={hasMetricData('mongodb_cursor_timed_out_count') ? 'spark' : 'none'} trend={metricMap.mongodb_cursor_timed_out_count?.viewData || []} color={metricColor('mongodb_cursor_timed_out_count')} />
                  <DetailMetricRow styles={styles} label="用户断言" guide={[{ label: '用户断言', detail: '因非法请求 / 参数抛出的错误累计次数;持续增长说明客户端有问题请求。' }]} value={renderMetricValue('mongodb_assert_user', formatMetricValue(userAssert, 'counts').value)} viz={hasMetricData('mongodb_assert_user') ? 'spark' : 'none'} trend={metricMap.mongodb_assert_user?.viewData || []} color={metricColor('mongodb_assert_user')} />
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
                  collectionInterval={currentInstanceInterval}
                  hideTimeSelector
                  onExternalXRangeChange={onXRangeChange}
                />
              </DashboardPanel>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
