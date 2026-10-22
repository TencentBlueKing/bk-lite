'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { DatabaseOutlined } from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import { useTranslation } from '@/utils/i18n';
import { TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import {
  DASHBOARD_METRICS,
  MYSQL_COLLECTION_STATUS_QUERY
} from './config';
import { MetricSeries, MetricUnit, MysqlMetricConfig } from './types';
import styles from './index.module.scss';
import hostChrome from '../host/index.module.scss';
import useMonitorApi from '@/app/monitor/api';
import {
  DEFAULT_REFRESH_FREQUENCY_LIST,
  fetchDashboardInstancePages,
  buildSearchParams,
  buildPreviousPeriodTimeValues,
  runWithConcurrency,
  normalizeDisplayText,
  isOpaqueIdentifier,
  buildInstanceDisplayName,
  buildInstanceSearchTokens,
  resolveDashboardInstanceIdentity,
  resolveDashboardInstanceIdValues,
  encodeInstanceIdValuesParam,
  isInstanceOptionForIdentity,
  resolveCollectionStatusRange,
  freezeTimeValues,
  toMetricSeries,
  useLoadSequence,
  INSTANCE_INTERVAL_WAIT_MS,
  shouldWaitForInstanceInterval,
  beginMetricQueryAbort,
  isMetricQueryAborted
} from '../../shared/utils';
import {
  DashboardPageHeader,
  DashboardInstanceCard,
  DashboardPanel
} from '../../shared/widgets';
import {
  dashboardModeOptions,
  resolveObjectDashboardMode,
  writeObjectDashboardMode
} from '../../shared/utils/pro-dashboard';
import MysqlProLayout from './layered/mysql-pro-layout';
import { MysqlInstanceBadges } from './layered/instance-identity';
import { useMysqlLinkedHost } from './layered/use-linked-host';
import { MYSQL_PERF_AUX_METRICS, MYSQL_REPLICATION_EXTRA_METRICS, readMysqlHeaderIdentity, readMysqlProHeader } from './layered/ia';
import {
  MYSQL_FOCUS_METRICS,
  MYSQL_HEADER_METRICS,
  MYSQL_HEALTH_METRICS,
  MYSQL_ROLE_METRICS,
  blocksUntilReady
} from './layered/section-loading';
import MysqlLegacyLayout from './legacy-layout';

interface MysqlInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
  interval?: number;
  nodeId?: string;
  ip?: string;
}

type MysqlDisplayMode = 'dashboard' | 'metrics' | 'category';

const MYSQL_REFRESH_FREQUENCY_LIST = DEFAULT_REFRESH_FREQUENCY_LIST;
const METRIC_QUERY_CONCURRENCY = 4;
const MYSQL_METRIC_GROUPS = [
  {
    key: 'summary',
    names: [
      'mysql_uptime',
      'mysql_threads_connected',
      'mysql_threads_running',
      'mysql_variables_max_connections',
      'mysql_connection_utilization',
      'mysql_queries_rate',
      'mysql_slow_queries_rate',
      'mysql_com_select_rate',
      'mysql_innodb_row_lock_waits_rate',
      'mysql_buffer_pool_hit_ratio',
      'mysql_buffer_pool_used_ratio',
      'mysql_buffer_pool_dirty_ratio',
      'mysql_variables_read_only',
      'mysql_variables_super_read_only',
      'mysql_variables_log_bin',
      'mysql_variables_log_slave_updates',
      'mysql_slave_seconds_behind_master',
      'mysql_slave_io_running',
      'mysql_slave_sql_running'
    ]
  },
  {
    key: 'flow',
    names: [
      'mysql_process_list_threads_idle',
      'mysql_process_list_threads_executing',
      'mysql_process_list_threads_sending_data',
      'mysql_process_list_threads_waiting_for_lock',
      'mysql_innodb_data_reads_rate',
      'mysql_innodb_data_writes_rate',
      'mysql_innodb_os_log_fsyncs_rate',
      'mysql_innodb_buffer_pool_pages_total',
      'mysql_innodb_buffer_pool_pages_dirty',
      'mysql_innodb_buffer_pool_pages_free',
      'mysql_created_tmp_tables_rate',
      'mysql_created_tmp_disk_tables_rate',
      'mysql_created_tmp_memory_tables_rate'
    ]
  },
  {
    key: 'trends',
    names: [
      'mysql_innodb_row_lock_time_avg',
      'mysql_com_insert_rate',
      'mysql_com_update_rate',
      'mysql_com_delete_rate',
      'mysql_bytes_received_rate',
      'mysql_bytes_sent_rate'
    ]
  },
  {
    key: 'details',
    names: [
      'mysql_opened_tables_rate',
      'mysql_table_open_cache_misses_rate',
      'mysql_aborted_connects',
      'mysql_aborted_connects_rate',
      'mysql_aborted_clients',
      'mysql_aborted_clients_rate',
      'mysql_connection_errors_internal',
      'mysql_connection_errors_max_connections',
      'mysql_connection_errors_max_connections_rate',
      'mysql_connection_errors_peer_address',
      'mysql_connection_errors_select',
      'mysql_connection_errors_tcpwrap'
    ]
  }
] as const;
const MYSQL_COMPARE_METRICS = [
  'mysql_connection_utilization',
  'mysql_queries_rate',
  'mysql_slow_queries_rate',
  'mysql_innodb_row_lock_waits_rate',
  'mysql_buffer_pool_hit_ratio'
];
const MYSQL_METRIC_CONFIG_BY_NAME = new Map(DASHBOARD_METRICS.map((metric) => [metric.name, metric]));
/** 专业盘只拉自己用到的指标。传统盘仍走 MYSQL_METRIC_GROUPS，互不影响。 */
const MYSQL_PRO_CHART_METRICS = [
  'mysql_com_insert_rate',
  'mysql_com_update_rate',
  'mysql_com_delete_rate',
  'mysql_innodb_data_reads_rate',
  'mysql_innodb_data_writes_rate',
  'mysql_innodb_os_log_fsyncs_rate',
  'mysql_variables_log_slave_updates'
] as const;
const MYSQL_CATEGORY_METRIC_NAMES = [...new Set([
  ...MYSQL_HEALTH_METRICS,
  'mysql_threads_running',
  ...MYSQL_HEADER_METRICS,
  ...MYSQL_FOCUS_METRICS,
  ...MYSQL_ROLE_METRICS,
  ...MYSQL_PERF_AUX_METRICS,
  ...MYSQL_REPLICATION_EXTRA_METRICS,
  ...MYSQL_PRO_CHART_METRICS
])].filter((name) => MYSQL_METRIC_CONFIG_BY_NAME.has(name));
const MYSQL_CATEGORY_PENDING_ALL: ReadonlySet<string> = new Set(MYSQL_CATEGORY_METRIC_NAMES);

export default function MysqlDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const loadSequence = useLoadSequence();
  const modeQuery = searchParams.toString();
  const [pendingMetricNames, setPendingMetricNames] = useState<ReadonlySet<string>>(() => new Set());
  const [displayMode, setDisplayMode] = useState<MysqlDisplayMode>(() => (
    resolveObjectDashboardMode('mysql', new URLSearchParams(modeQuery))
  ));
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
  const [queryTimeRange, setQueryTimeRange] = useState<{ startMs: number; endMs: number } | null>(null);
  const [proReloadKey, setProReloadKey] = useState(0);
  const [instanceOptions, setInstanceOptions] = useState<MysqlInstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [instanceListSettled, setInstanceListSettled] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);
  const [settledInstanceKey, setSettledInstanceKey] = useState('');
  const requestedInstanceKeyRef = useRef('');

  useEffect(() => {
    setDisplayMode(resolveObjectDashboardMode('mysql', new URLSearchParams(modeQuery)));
  }, [modeQuery]);

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || 'Mysql';
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || 'MySQL';
  const instanceIdentity = useMemo(
    () => resolveDashboardInstanceIdentity(new URLSearchParams(searchParams.toString())),
    [searchParams]
  );
  const instanceId: React.Key = instanceIdentity.instanceId;
  const instanceName = searchParams.get('instance_name') || '--';
  const idValues = instanceIdentity.idValues;
  const instanceIdKeys = (searchParams.get('instance_id_keys') || 'instance_id').split(',').filter(Boolean);
  const instanceIdText = normalizeDisplayText(idValues[0] || '');
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || 'MySQL';
  const isDashboardMode = displayMode === 'dashboard' || displayMode === 'category';
  const normalizedInstanceName = isOpaqueIdentifier(instanceName) ? '' : normalizeDisplayText(instanceName);

  useEffect(() => {
    if (!monitorObjectId) {
      setInstanceOptions([]);
      setInstanceListSettled(true);
      return;
    }

    let active = true;
    setInstanceListSettled(false);

    const loadInstances = async () => {
      try {
        setInstanceLoading(true);
        const data = await fetchDashboardInstancePages(getInstanceList, monitorObjectId);
        if (!active) {
          return;
        }

        const uniqueOptions = new Map<string, MysqlInstanceOption>();

        (data.results || []).forEach((item: any) => {
          const value = String(item.instance_id || '');
          if (!value || uniqueOptions.has(value)) {
            return;
          }

          const label = buildInstanceDisplayName(item);
          uniqueOptions.set(value, {
            label,
            value,
            instanceIdValues: resolveDashboardInstanceIdValues(item),
            searchTokens: buildInstanceSearchTokens(item, label),
            interval: Number(item.interval) || undefined,
            nodeId: String(item.node_id || '').trim(),
            ip: String(item.ip || '').trim()
          });
        });

        const results = Array.from(uniqueOptions.values());

        setInstanceOptions(results);
      } catch {
        if (active) {
          setInstanceOptions([]);
        }
      } finally {
        if (active) {
          setInstanceLoading(false);
          setInstanceListSettled(true);
        }
      }
    };

    loadInstances();

    return () => {
      active = false;
    };
  }, [monitorObjectId]);

  useEffect(() => () => {
    loadAbortRef.current?.abort();
  }, []);

  const idValuesKey = JSON.stringify(idValues);
  const currentInstanceCandidates = instanceOptions.filter((item) =>
    isInstanceOptionForIdentity(item, instanceId, idValues)
  );
  const currentInstanceOption =
    currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) ||
    currentInstanceCandidates.find((item) => !isOpaqueIdentifier(item.label)) ||
    currentInstanceCandidates[0];
  const resolvedInstanceName =
    currentInstanceOption?.label || normalizedInstanceName || instanceIdText || '--';
  const currentInstanceInterval = currentInstanceOption?.interval;
  const primaryInstanceText = resolvedInstanceName;

  const queryRangeSeries = async (
    metric: MysqlMetricConfig,
    targetTimeValues: TimeValuesProps,
    signal?: AbortSignal
  ): Promise<MetricSeries> => {
    const params = buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, targetTimeValues, undefined, false, currentInstanceInterval, {
      monitorObjectId,
      instanceId,
    });
    try {
      const result = signal
        ? await getInstanceQuery(params, { signal })
        : await getInstanceQuery(params);
      return toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys);
    } catch {
      return { ...metric, viewData: [], loadState: 'error' };
    }
  };

  const loadMetricGroup = async (
    metricNames: readonly string[],
    targetTimeValues: TimeValuesProps,
    onMetric?: (name: string, series: MetricSeries) => void,
    signal?: AbortSignal
  ) => {
    const metrics = metricNames
      .map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name))
      .filter((metric): metric is MysqlMetricConfig => Boolean(metric));

    return runWithConcurrency(
      metrics,
      METRIC_QUERY_CONCURRENCY,
      async (metric) => {
        const series = await queryRangeSeries(metric, targetTimeValues, signal);
        if (!isMetricQueryAborted(signal)) onMetric?.(metric.name, series);
        return [metric.name, series] as [string, MetricSeries];
      },
      signal
    );
  };

  const loadCategoryMetrics = async (silent: boolean) => {
    const abortController = beginMetricQueryAbort(loadAbortRef.current);
    loadAbortRef.current = abortController;
    const signal = abortController.signal;
    const loadSeq = loadSequence.begin();
    const nextInstanceKey = `${String(instanceId)}|${idValuesKey}`;
    const switchingInstance = requestedInstanceKeyRef.current !== nextInstanceKey;
    requestedInstanceKeyRef.current = nextInstanceKey;
    const fresh = !silent || switchingInstance;

    if (fresh) {
      setSeries({});
      setPreviousSeries({});
      if (switchingInstance) setCollectionStatusMetric(null);
      setPendingMetricNames(new Set(MYSQL_CATEGORY_METRIC_NAMES));
      setSettledInstanceKey(nextInstanceKey);
    }

    if (!idValues.length) {
      setSeries({});
      setPreviousSeries({});
      setCollectionStatusMetric(null);
      setPendingMetricNames(new Set());
      setSettledInstanceKey(nextInstanceKey);
      return;
    }

    const frozenTimeValues = freezeTimeValues(timeValues);
    const frozenRange = resolveCollectionStatusRange(frozenTimeValues);
    if (frozenRange) setQueryTimeRange(frozenRange);
    const previousTimeValues = buildPreviousPeriodTimeValues(frozenTimeValues);
    const compareMetrics = MYSQL_COMPARE_METRICS
      .map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name))
      .filter((metric): metric is MysqlMetricConfig => Boolean(metric));
    const currentMetrics = MYSQL_CATEGORY_METRIC_NAMES
      .map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name))
      .filter((metric): metric is MysqlMetricConfig => Boolean(metric));

    if (fresh) setPreviousSeries({});

    const stillCurrent = () => loadSequence.isCurrent(loadSeq) && !isMetricQueryAborted(signal);

    const publish = (name: string, series: MetricSeries) => {
      if (!stillCurrent()) return;
      setSeries((prev) => (stillCurrent() ? { ...prev, [name]: series } : prev));
      if (!fresh) return;
      setPendingMetricNames((prev) => {
        if (!stillCurrent() || !prev.has(name)) return prev;
        const next = new Set(prev);
        next.delete(name);
        return next;
      });
    };

    const collectionMetric: MysqlMetricConfig = {
      name: 'mysql_collection_status',
      display_name: '采集状态',
      description: 'MySQL 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
      unit: 'counts',
      query: MYSQL_COLLECTION_STATUS_QUERY,
      color: '#27c274'
    };

    type CategoryJob =
      | { kind: 'current'; metric: MysqlMetricConfig }
      | { kind: 'previous'; metric: MysqlMetricConfig }
      | { kind: 'collection' };
    const jobs: CategoryJob[] = [
      { kind: 'collection' },
      ...currentMetrics.map((metric) => ({ kind: 'current' as const, metric })),
      ...(previousTimeValues
        ? compareMetrics.map((metric) => ({ kind: 'previous' as const, metric }))
        : [])
    ];

    await runWithConcurrency(jobs, METRIC_QUERY_CONCURRENCY, async (job) => {
      if (isMetricQueryAborted(signal) || !loadSequence.isCurrent(loadSeq)) return;
      if (job.kind === 'collection') {
        const params = buildSearchParams(MYSQL_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, frozenTimeValues, undefined, false, currentInstanceInterval, {
          monitorObjectId,
          instanceId,
        });
        let collectionStatus: MetricSeries;
        try {
          const result = await getInstanceQuery(params, { signal });
          collectionStatus = toMetricSeries(collectionMetric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys);
        } catch {
          collectionStatus = { ...collectionMetric, viewData: [], loadState: 'error' };
        }
        if (!stillCurrent()) return;
        setCollectionStatusMetric((prev) => (stillCurrent() ? collectionStatus : prev));
        return;
      }
      const targetTimeValues = job.kind === 'previous' && previousTimeValues
        ? previousTimeValues
        : frozenTimeValues;
      const series = await queryRangeSeries(job.metric, targetTimeValues, signal);
      if (!stillCurrent()) return;
      if (job.kind === 'current') {
        publish(job.metric.name, series);
        return;
      }
      setPreviousSeries((prev) => (stillCurrent() ? { ...prev, [job.metric.name]: series } : prev));
    }, signal);
  };

  const loadMetrics = async (silent = false) => {
    if (displayMode === 'category') {
      await loadCategoryMetrics(silent);
      return;
    }
    const loadSeq = loadSequence.begin();
    const nextInstanceKey = `${String(instanceId)}|${idValuesKey}`;
    requestedInstanceKeyRef.current = nextInstanceKey;
    let committed = false;

    try {
      if (isDashboardMode) {
        if (!idValues.length) {
          setSeries({});
          setPreviousSeries({});
          setCollectionStatusMetric(null);
          setSettledInstanceKey(nextInstanceKey);
          committed = true;
          return;
        }
        const frozenTimeValues = freezeTimeValues(timeValues);
        const frozenRange = resolveCollectionStatusRange(frozenTimeValues);
        if (frozenRange) setQueryTimeRange(frozenRange);
        const previousTimeValues = buildPreviousPeriodTimeValues(frozenTimeValues);
        const compareMetrics = MYSQL_COMPARE_METRICS.map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name)).filter(
          (metric): metric is MysqlMetricConfig => Boolean(metric)
        );
        const summaryResultsPromise = loadMetricGroup(MYSQL_METRIC_GROUPS[0].names, frozenTimeValues);

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(buildSearchParams(MYSQL_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, frozenTimeValues, undefined, false, currentInstanceInterval, {
          monitorObjectId,
          instanceId,
        }))
          .then((result) =>
            toMetricSeries(
              {
                name: 'mysql_collection_status',
                display_name: '采集状态',
                description: 'MySQL 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts',
                query: MYSQL_COLLECTION_STATUS_QUERY,
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
                name: 'mysql_collection_status',
                display_name: '采集状态',
                description: 'MySQL 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts' as MetricUnit,
                query: MYSQL_COLLECTION_STATUS_QUERY,
                color: '#27c274',
                viewData: [],
                loadState: 'error' as const
              } satisfies MetricSeries)
          );

        const previousMetricResultsPromise = previousTimeValues
          ? runWithConcurrency(
            compareMetrics,
            METRIC_QUERY_CONCURRENCY,
            async (metric) =>
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues, undefined, false, currentInstanceInterval, {
                monitorObjectId,
                instanceId,
              }))
                .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
                .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
          : Promise.resolve([] as Array<readonly [string, MetricSeries]>);

        if (!silent) {
          setPreviousSeries({});
        }

        previousMetricResultsPromise.then((previousResults) => {
          if (!loadSequence.isCurrent(loadSeq)) {
            return;
          }
          setPreviousSeries(Object.fromEntries(previousResults));
        });

        const [summaryResults, collectionStatus] = await Promise.all([
          summaryResultsPromise,
          collectionStatusPromise
        ]);

        if (!loadSequence.isCurrent(loadSeq)) {
          return;
        }

        setSeries((prev) => (silent ? { ...prev, ...Object.fromEntries(summaryResults) } : Object.fromEntries(summaryResults)));
        setCollectionStatusMetric(collectionStatus);
        setSettledInstanceKey(nextInstanceKey);
        committed = true;

        MYSQL_METRIC_GROUPS.slice(1).forEach((group) => {
          loadMetricGroup(group.names, frozenTimeValues).then((results) => {
            if (!loadSequence.isCurrent(loadSeq)) {
              return;
            }

            setSeries((prev) => ({ ...prev, ...Object.fromEntries(results) }));
          });
        });
      } else {
        setSeries({});
        setPreviousSeries({});
        setCollectionStatusMetric(null);
      }
    } finally {
      if (loadSequence.isCurrent(loadSeq) && !committed) {
        setSettledInstanceKey(nextInstanceKey);
      }
    }
  };

  useEffect(() => {
    if (displayMode === 'category' || !isDashboardMode) return;
    loadMetrics();
  }, [currentInstanceInterval, instanceId, idValuesKey, timeValues, isDashboardMode, displayMode]);

  useEffect(() => {
    if (displayMode !== 'category') {
      loadAbortRef.current?.abort();
      return;
    }
    if (shouldWaitForInstanceInterval({
      hasInstanceIds: idValues.length > 0,
      instanceInterval: currentInstanceInterval,
      instanceListSettled
    })) {
      loadAbortRef.current?.abort();
      const timer = window.setTimeout(() => {
        void loadMetrics();
      }, INSTANCE_INTERVAL_WAIT_MS);
      return () => window.clearTimeout(timer);
    }
    void loadMetrics();
  }, [currentInstanceInterval, instanceId, idValuesKey, timeValues, displayMode, instanceListSettled]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (isDashboardMode && frequence > 0) {
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
  }, [currentInstanceInterval, frequence, timeValues, instanceId, idValuesKey, isDashboardMode, displayMode]);

  const metricMap = useMemo(() => series, [series]);
  const dashboardMetrics = useMemo(
    () => DASHBOARD_METRICS.map((metric) => metricMap[metric.name] || { ...metric, viewData: [], loadState: 'success' as const }),
    [metricMap]
  );

  const previousMetricMap = useMemo(() => previousSeries, [previousSeries]);

  // 专业态与传统态共用同一页标题，对齐主机「主机监控仪表盘」。
  const pageTitle = displayMode === 'metrics'
    ? `${objectDisplayText} 全量指标`
    : 'MySQL 监控仪表盘';
  const hasDashboardContent = dashboardMetrics.length > 0;
  const showEmpty = isDashboardMode ? !hasDashboardContent : false;

  const chrome = displayMode === 'category' ? hostChrome : styles;
  const instanceKey = `${String(instanceId)}|${idValuesKey}`;
  const instanceSwitching = displayMode === 'category' && settledInstanceKey !== instanceKey;
  const proMetricMap = instanceSwitching ? {} : metricMap;
  const proPreviousMetricMap = instanceSwitching ? {} : previousMetricMap;
  const proPending = instanceSwitching ? MYSQL_CATEGORY_PENDING_ALL : pendingMetricNames;
  const mysqlIdentity = readMysqlHeaderIdentity(metricMap, resolvedInstanceName);
  const proMode = displayMode === 'category';
  const linkedHost = useMysqlLinkedHost(
    currentInstanceOption?.nodeId || '',
    currentInstanceOption?.ip || '',
    proMode && !instanceLoading
  );
  const hostPending = instanceLoading || linkedHost.pending;
  const identityPending = blocksUntilReady(MYSQL_HEADER_METRICS, proPending);
  const identityHeader = identityPending ? null : readMysqlProHeader(proMetricMap);
  // 实例 ID 与展示名仅分隔符不同时（mysql_3306 vs mysql-3306）视为重复，不再展示。
  const normalizeIdentityKey = (value: string) => value.trim().toLowerCase().replace(/[-_\s]+/g, '');
  const showInstanceId =
    Boolean(instanceIdText) &&
    normalizeIdentityKey(instanceIdText) !== normalizeIdentityKey(primaryInstanceText);
  // 专业盘身份在标题下的灰字行。传统盘与全量指标仍用拓扑身份和时区。
  const mysqlDisplayTimezone = 'Asia/Shanghai';
  const classicIdentityMeta = mysqlIdentity.deployment === '单节点'
    ? [
      <span key="topology" className={chrome.instanceMetaInline}>
        单节点
      </span>
    ]
    : [
      <span key="topology" className={chrome.instanceMetaInline}>
        主从复制
      </span>,
      <span key="role" className={`${styles.identityPill} ${styles.identityPillRole}`}>
        {mysqlIdentity.role}
      </span>
    ];
  const instanceMetaItems = (proMode
    ? [
      <MysqlInstanceBadges
        key="pro-identity"
        header={identityHeader}
        pending={identityPending}
        host={linkedHost.host}
        hostHref={linkedHost.href}
        hostPending={hostPending}
      />
    ]
    : [
      <span key="object-name" className={chrome.instanceMetaInline}>
        {objectDisplayText}
      </span>,
      showInstanceId ? (
        <span key="instance-id" className={chrome.instanceMetaMuted}>
          {instanceIdText}
        </span>
      ) : null,
      ...classicIdentityMeta,
      <span key="timezone" className={chrome.instanceMetaMuted}>
        时区 {mysqlDisplayTimezone}
      </span>
    ]).filter(Boolean) as React.ReactNode[];
  const metricsOverviewGuide = [
    { label: '监控指标全景', detail: '这里承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' },
    { label: '适用场景', detail: '如果仪表盘只给出方向，这里负责补足细节与完整上下文。' }
  ];
  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({
      timeRange: val,
      originValue
    });
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

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const refreshDashboard = () => {
    if (!isDashboardMode) {
      setMetricsRefreshSignal((value) => value + 1);
      return;
    }
    if (displayMode === 'category') setProReloadKey((value) => value + 1);
    loadMetrics();
  };

  const onInstanceChange = (value: string) => {
    const target = instanceOptions.find((item) => item.value === value);
    const params = new URLSearchParams(searchParams.toString());
    params.set('instance_id', value);
    params.set('instance_name', String(target?.label || value));
    params.set('instance_id_values', encodeInstanceIdValuesParam(
      target?.instanceIdValues?.length
        ? target.instanceIdValues
        : resolveDashboardInstanceIdValues({ instance_id: value }),
    ));
    router.push(`/monitor/view/dashboard/mysql?${params.toString()}`);
  };

  const proChrome = displayMode === 'category';
  return (
    <div
      className={proChrome ? `${chrome.page} ${styles.proPage}` : chrome.page}
      data-mysql-chrome={proChrome ? 'host' : 'classic'}
    >
      <div className={proChrome ? `${chrome.shell} ${styles.proShell}` : chrome.shell}>
        <div className={chrome.unifiedShell} data-dashboard-shell="unified">
          <div className={chrome.pageIntro}>
          <DashboardPageHeader
            title={pageTitle}
            displayMode={displayMode}
            onDisplayModeChange={(mode) => {
              const next = String(mode);
              if (next !== 'dashboard' && next !== 'metrics' && next !== 'category') return;
              setDisplayMode(next);
              const params = writeObjectDashboardMode(new URLSearchParams(searchParams.toString()), next);
              router.replace(`?${params.toString()}`, { scroll: false });
            }}
            modeControl="pill"
            modeOptions={dashboardModeOptions('mysql')}
            timeDefaultValue={timeDefaultValue}
            frequencyList={MYSQL_REFRESH_FREQUENCY_LIST}
            onTimeChange={onTimeChange}
            onFrequenceChange={onFrequenceChange}
            onRefresh={refreshDashboard}
            showTimeSelector={false}
            styles={chrome}
          />
          </div>
          <div className={chrome.unifiedHostBar}>
          <DashboardInstanceCard
            instanceName={primaryInstanceText}
            metaItems={instanceMetaItems}
            icon={<DatabaseOutlined />}
            selectorValue={currentInstanceOption?.value || (instanceIdText ? String(instanceId) : undefined)}
            selectorLoading={instanceLoading}
            selectorOptions={instanceOptions}
            onInstanceChange={onInstanceChange}
            selectorPlaceholder="选择实例"
            selectorTitle={currentInstanceOption?.label || resolvedInstanceName}
            isDashboardMode={isDashboardMode}
            timeSelectorProps={{
              timeDefaultValue,
              frequencyList: MYSQL_REFRESH_FREQUENCY_LIST,
              onTimeChange,
              onFrequenceChange,
              onRefresh: refreshDashboard
            }}
            styles={chrome}
          />
          </div>
        </div>

        <div className={chrome.unifiedBelow}>
          {showEmpty ? (
            <div className={styles.empty}>
              <CompactEmptyState description={t('common.noData')} />
            </div>
          ) : (
            <>
              {displayMode === 'dashboard' ? (
                <MysqlLegacyLayout
                  metricMap={metricMap}
                  previousMetricMap={previousMetricMap}
                  collectionStatusMetric={collectionStatusMetric}
                  queryTimeRange={queryTimeRange}
                  timeValues={timeValues}
                  currentInstanceInterval={currentInstanceInterval}
                  resolvedInstanceName={resolvedInstanceName}
                  onXRangeChange={onXRangeChange}
                />
              ) : displayMode === 'category' ? (
                <div className={styles.modeContent} data-mysql-body="pro">
                  <MysqlProLayout
                    key={instanceKey}
                    metricMap={proMetricMap}
                    previousMetricMap={proPreviousMetricMap}
                    pendingMetricNames={proPending}
                    instanceId={String(instanceId || '')}
                    monitorObjectId={monitorObjectId}
                    instanceName={resolvedInstanceName}
                    idValues={idValues}
                    instanceIdKeys={instanceIdKeys}
                    timeValues={timeValues}
                    queryTimeRange={queryTimeRange}
                    reloadKey={proReloadKey}
                    minStepSeconds={currentInstanceInterval}
                  />
                </div>
              ) : (
                <div className={`${styles.modeContent} ${styles.metricsMode}`} data-mysql-body="metrics">
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
