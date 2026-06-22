'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Empty, Tag } from 'antd';
import {
  DatabaseOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  NodeIndexOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import { useTranslation } from '@/utils/i18n';
import { TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import {
  DASHBOARD_METRICS,
  MYSQL_COLLECTION_STATUS_QUERY,
  TREND_LEGENDS
} from './config';
import { MetricSeries, MetricUnit, MysqlMetricConfig } from './types';
import styles from './index.module.scss';
import useMonitorApi from '@/app/monitor/api';
import {
  DEFAULT_REFRESH_FREQUENCY_LIST,
  formatMetricValue,
  buildSearchParams,
  getLatestChartValue,
  buildSeriesTotalByTime,
  buildPreviousPeriodTimeValues,
  runWithConcurrency,
  getPeriodCompare,
  normalizeDisplayText,
  isOpaqueIdentifier,
  buildInstanceDisplayName,
  buildInstanceSearchTokens,
  parseLegacyParamList,
  buildCollectionStatusTimeline,
  toMetricSeries,
  buildMetricItem,
  mergeChartSeries,
  getCollectionStatus,
  useLoadSequence
} from '../../shared/utils';
import {
  StatCard,
  CollectionStatusCard,
  TitleWithGuide,
  DashboardPageHeader,
  DashboardInstanceCard,
  DashboardPanel,
  TrendChartPanel,
  RingChartPanel,
  HorizontalBarPanel
} from '../../shared/widgets';
import { countRestartsInRange } from '../common/simple-dashboard-core';

interface MysqlInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
  interval?: number;
}

const MYSQL_REFRESH_FREQUENCY_LIST = DEFAULT_REFRESH_FREQUENCY_LIST;
const RAW_VALUE_METRICS = new Set([
  'mysql_uptime',
  'mysql_innodb_buffer_pool_pages_total',
  'mysql_innodb_buffer_pool_pages_free',
  'mysql_innodb_buffer_pool_pages_dirty',
  // 字节速率(byteps)与字节配置项(bytes):禁用服务端自动换算,避免与前端双重换算
  'mysql_bytes_received',
  'mysql_bytes_sent',
  'mysql_variables_innodb_buffer_pool_size',
  'mysql_variables_tmp_table_size',
  'mysql_variables_max_heap_table_size'
]);
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

const getLatestThreadSnapshot = (metricMap: Record<string, MetricSeries | undefined>) => {
  const connectedByTime = buildSeriesTotalByTime(metricMap.mysql_threads_connected?.viewData || []);
  const sleepByTime = buildSeriesTotalByTime(metricMap.mysql_process_list_threads_idle?.viewData || []);
  const queryByTime = buildSeriesTotalByTime(metricMap.mysql_process_list_threads_executing?.viewData || []);
  const sendingByTime = buildSeriesTotalByTime(metricMap.mysql_process_list_threads_sending_data?.viewData || []);
  const lockedByTime = buildSeriesTotalByTime(metricMap.mysql_process_list_threads_waiting_for_lock?.viewData || []);
  const allTimes = Array.from(
    new Set([
      ...connectedByTime.keys(),
      ...sleepByTime.keys(),
      ...queryByTime.keys(),
      ...sendingByTime.keys(),
      ...lockedByTime.keys()
    ])
  ).sort((a, b) => b - a);

  const latestConnected = allTimes.find((time) => connectedByTime.has(time));
  const latestConnectedCount = latestConnected === undefined ? 0 : connectedByTime.get(latestConnected) || 0;
  const activeTime = allTimes.find((time) => {
    const knownTotal =
      (sleepByTime.get(time) || 0) +
      (queryByTime.get(time) || 0) +
      (sendingByTime.get(time) || 0) +
      (lockedByTime.get(time) || 0);

    return knownTotal > 0;
  });
  const snapshotTime = activeTime ?? allTimes[0];

  if (snapshotTime === undefined) {
    return {
      connected: 0,
      sleep: 0,
      query: 0,
      sending: 0,
      locked: 0
    };
  }

  const sleep = sleepByTime.get(snapshotTime) || 0;
  const query = queryByTime.get(snapshotTime) || 0;
  const sending = sendingByTime.get(snapshotTime) || 0;
  const locked = lockedByTime.get(snapshotTime) || 0;
  const knownTotal = sleep + query + sending + locked;
  const connected = Math.max(connectedByTime.get(snapshotTime) || latestConnectedCount, knownTotal);

  return {
    connected,
    sleep,
    query,
    sending,
    locked
  };
};

const getUptimeInsight = (uptimeSeconds: number) => {
  if (!Number.isFinite(uptimeSeconds) || uptimeSeconds < 0) {
    return {
      startupTimeText: '--',
      uptimeText: '--'
    };
  }

  const startedAt = dayjs().subtract(Math.floor(uptimeSeconds), 'second');
  const uptimeDisplay = formatMetricValue(uptimeSeconds, 's');

  return {
    startupTimeText: startedAt.format('YYYY-MM-DD HH:mm:ss'),
    uptimeText: `${uptimeDisplay.value}${uptimeDisplay.unit || ''}`
  };
};

const inferMysqlIdentity = (roleSignals: {
  instanceName: string;
  hasReplicationMetrics: boolean;
  logSlaveUpdates: number;
}) => {
  const { instanceName, hasReplicationMetrics, logSlaveUpdates } = roleSignals;
  const normalizedName = instanceName.toLowerCase();
  const nameSaysStandalone = /单点|单节点|独立|standalone|single/.test(normalizedName);
  const nameSaysReplica = /从库|从节点|slave|replica|secondary/.test(normalizedName);
  const nameSaysPrimary = /主库|主节点|master|primary/.test(normalizedName);

  // 从库判据的 ground truth:SHOW SLAVE STATUS 有行(hasReplicationMetrics),名称作兜底。
  // 刻意不把 read_only / super_read_only 单独当作从库信号 —— 主库也可能被临时设为只读,
  // 据此会把只读主库误判成从库、进而误报"复制已停止"。运行中的从库本就有 slave 状态行,已被覆盖。
  const hasReplicaIdentity = hasReplicationMetrics || nameSaysReplica;
  // 是否处于主从拓扑:本身是从库,或名称/配置(回放写日志 log_slave_updates)表明它是拓扑中的主库。
  const inReplicationTopology = hasReplicaIdentity || nameSaysPrimary || logSlaveUpdates > 0;
  const deployment = nameSaysStandalone || !inReplicationTopology ? '单节点' : '主从复制';
  const role = hasReplicaIdentity ? '从库' : deployment === '主从复制' ? '主库' : '独立实例';
  const replication = role === '从库' ? '从库复制' : role === '主库' ? '源端复制' : '不适用';

  return { deployment, role, replication };
};

// 每分钟计数率缩写显示:127051380 → "127Mil/min",避免长数字稀释可读性。
const formatPerMinute = (perMin: number): string => {
  const { value, unit } = formatMetricValue(perMin, 'counts');
  return `${value}${unit}/min`;
};

export default function MysqlDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const loadSequence = useLoadSequence();
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
  const [instanceOptions, setInstanceOptions] = useState<MysqlInstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);

  const monitorObjectId = searchParams.get('monitorObjId') || '';
  const monitorObjectName = searchParams.get('name') || 'Mysql';
  const monitorObjDisplayName = searchParams.get('monitorObjDisplayName') || 'MySQL';
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
  const instanceIdText = normalizeDisplayText(String(instanceId));
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || 'MySQL';
  const isDashboardMode = displayMode === 'dashboard';
  const normalizedInstanceName = isOpaqueIdentifier(instanceName) ? '' : normalizeDisplayText(instanceName);

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

        const uniqueOptions = new Map<string, MysqlInstanceOption>();

        (data?.results || []).forEach((item: any) => {
          const value = String(item.instance_id || '');
          if (!value || uniqueOptions.has(value)) {
            return;
          }

          const label = buildInstanceDisplayName(item);
          uniqueOptions.set(value, {
            label,
            value,
            instanceIdValues: Array.isArray(item.instance_id_values) && item.instance_id_values.length ? item.instance_id_values : [value],
            searchTokens: buildInstanceSearchTokens(item, label),
            interval: Number(item.interval) || undefined
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
  const currentInstanceOption =
    currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) ||
    currentInstanceCandidates.find((item) => !isOpaqueIdentifier(item.label)) ||
    currentInstanceCandidates[0];
  const resolvedInstanceName =
    currentInstanceOption?.label || normalizedInstanceName || normalizeDisplayText(String(instanceId)) || normalizeDisplayText(idValues[0]) || '--';
  const currentInstanceInterval = currentInstanceOption?.interval;
  const primaryInstanceText = resolvedInstanceName;

  const loadMetricGroup = async (metricNames: readonly string[], targetTimeValues: TimeValuesProps) => {
    const metrics = metricNames
      .map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name))
      .filter((metric): metric is MysqlMetricConfig => Boolean(metric));

    return runWithConcurrency(
      metrics,
      METRIC_QUERY_CONCURRENCY,
      async (metric) =>
        getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, targetTimeValues, RAW_VALUE_METRICS, undefined, currentInstanceInterval))
          .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
          .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
    );
  };

  const loadMetrics = async (silent = false) => {
    const loadSeq = loadSequence.begin();

    if (!silent) {
      setLoading(true);
    }

    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = MYSQL_COMPARE_METRICS.map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name)).filter(
          (metric): metric is MysqlMetricConfig => Boolean(metric)
        );
        const summaryResultsPromise = loadMetricGroup(MYSQL_METRIC_GROUPS[0].names, timeValues);

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(buildSearchParams(MYSQL_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues, RAW_VALUE_METRICS, undefined, currentInstanceInterval))
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
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues, RAW_VALUE_METRICS, undefined, currentInstanceInterval))
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

        if (!silent) {
          setLoading(false);
        }

        MYSQL_METRIC_GROUPS.slice(1).forEach((group) => {
          loadMetricGroup(group.names, timeValues).then((results) => {
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
      if (loadSequence.isCurrent(loadSeq)) {
        setLoading(false);
      }
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
  }, [currentInstanceInterval, frequence, timeValues, instanceId, idValuesKey, isDashboardMode]);

  const metricMap = useMemo(() => series, [series]);
  const dashboardMetrics = useMemo(
    () => DASHBOARD_METRICS.map((metric) => metricMap[metric.name] || { ...metric, viewData: [], loadState: 'success' as const }),
    [metricMap]
  );

  const previousMetricMap = useMemo(() => previousSeries, [previousSeries]);

  const getLatest = (name: string) => {
    const target = metricMap[name];
    return getLatestChartValue(target?.viewData || []);
  };

  const getPreviousLatest = (name: string) => {
    const target = previousMetricMap[name];
    return getLatestChartValue(target?.viewData || []);
  };

  const hasMetricData = (name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  };

  const getDisplayValue = (name: string, display: { value: string; unit: string }) => ({
    value: hasMetricData(name) ? display.value : '--',
    unit: hasMetricData(name) ? display.unit : ''
  });

  const renderMetricValue = (name: string, value: string) => (hasMetricData(name) ? value : '--');

  const qpsValue = getLatest('mysql_queries_rate');
  const connValue = getLatest('mysql_connection_utilization');
  const slowValue = getLatest('mysql_slow_queries_rate');
  const uptimeValue = getLatest('mysql_uptime');
  const threadsConnectedValue = getLatest('mysql_threads_connected');
  const maxConnectionsValue = getLatest('mysql_variables_max_connections');
  const bpUsedValue = getLatest('mysql_buffer_pool_used_ratio');
  const bpDirtyValue = getLatest('mysql_buffer_pool_dirty_ratio');
  const dataReadValue = getLatest('mysql_innodb_data_reads_rate');
  const dataWriteValue = getLatest('mysql_innodb_data_writes_rate');
  const fsyncValue = getLatest('mysql_innodb_os_log_fsyncs_rate');
  const selectValue = getLatest('mysql_com_select_rate');
  const insertValue = getLatest('mysql_com_insert_rate');
  const updateValue = getLatest('mysql_com_update_rate');
  const deleteValue = getLatest('mysql_com_delete_rate');
  const tmpDiskRate = getLatest('mysql_created_tmp_disk_tables_rate');
  const tmpTotalRate = getLatest('mysql_created_tmp_tables_rate');
  const lockWait = getLatest('mysql_innodb_row_lock_time_avg');
  const lockWaitRate = getLatest('mysql_innodb_row_lock_waits_rate');
  const openedTablesRate = getLatest('mysql_opened_tables_rate');
  const tableCacheMissRate = getLatest('mysql_table_open_cache_misses_rate');
  const abortedConnectsRate = getLatest('mysql_aborted_connects_rate');
  const abortedClientsRate = getLatest('mysql_aborted_clients_rate');
  const internalConnectionErrors = getLatest('mysql_connection_errors_internal');
  const maxConnectionErrorsRate = getLatest('mysql_connection_errors_max_connections_rate');
  const replicationIoRunning = getLatest('mysql_slave_io_running');
  const replicationSqlRunning = getLatest('mysql_slave_sql_running');
  const logBinValue = getLatest('mysql_variables_log_bin');
  const logSlaveUpdatesValue = getLatest('mysql_variables_log_slave_updates');
  const statusInfo = getCollectionStatus(collectionStatusMetric);
  const metricEmptyText = statusInfo.label === '异常' ? '查询失败' : '暂无采集数据';
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric?.loadState, collectionStatusMetric?.viewData);
  const qpsDisplay = formatMetricValue(qpsValue, 'cps');
  const connDisplay = formatMetricValue(connValue, 'percent');
  const slowDisplay = formatMetricValue(slowValue, 'cps');
  const uptimeInsight = getUptimeInsight(uptimeValue);
  const connCompare = getPeriodCompare(connValue, getPreviousLatest('mysql_connection_utilization'));
  const qpsCompare = getPeriodCompare(qpsValue, getPreviousLatest('mysql_queries_rate'));
  const slowCompare = getPeriodCompare(slowValue, getPreviousLatest('mysql_slow_queries_rate'));
  const lockWaitRateCompare = getPeriodCompare(lockWaitRate, getPreviousLatest('mysql_innodb_row_lock_waits_rate'));
  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : 'MySQL 监控仪表盘';
  const hasDashboardContent = dashboardMetrics.length > 0;
  const showEmpty = isDashboardMode ? !hasDashboardContent : false;

  const qpsTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_queries_rate',
          label: 'QPS',
          displayName: 'QPS',
          data: metricMap.mysql_queries_rate?.viewData || []
        },
        {
          key: 'mysql_slow_queries_rate',
          label: '慢查询速率',
          displayName: '慢查询速率',
          data: metricMap.mysql_slow_queries_rate?.viewData || []
        }
      ]),
    [metricMap.mysql_queries_rate?.viewData, metricMap.mysql_slow_queries_rate?.viewData]
  );

  const lockWaitTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_innodb_row_lock_waits_rate',
          label: '行锁等待速率（次/秒）',
          displayName: '行锁等待速率',
          data: metricMap.mysql_innodb_row_lock_waits_rate?.viewData || []
        }
      ]),
    [metricMap.mysql_innodb_row_lock_waits_rate?.viewData]
  );

  const innodbTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_innodb_data_reads_rate',
          label: 'InnoDB 读 IOPS',
          displayName: 'InnoDB 读 IOPS',
          data: metricMap.mysql_innodb_data_reads_rate?.viewData || []
        },
        {
          key: 'mysql_innodb_data_writes_rate',
          label: 'InnoDB 写 IOPS',
          displayName: 'InnoDB 写 IOPS',
          data: metricMap.mysql_innodb_data_writes_rate?.viewData || []
        },
        {
          key: 'mysql_innodb_os_log_fsyncs_rate',
          label: 'Redo 刷盘',
          displayName: 'Redo 刷盘',
          data: metricMap.mysql_innodb_os_log_fsyncs_rate?.viewData || []
        }
      ]),
    [
      metricMap.mysql_innodb_data_reads_rate?.viewData,
      metricMap.mysql_innodb_data_writes_rate?.viewData,
      metricMap.mysql_innodb_os_log_fsyncs_rate?.viewData
    ]
  );

  const replicationTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_slave_seconds_behind_master',
          label: 'Replication_delay',
          displayName: '复制延迟',
          data: metricMap.mysql_slave_seconds_behind_master?.viewData || []
        }
      ]),
    [metricMap.mysql_slave_seconds_behind_master?.viewData]
  );

  const connTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_threads_connected',
          label: '当前连接数',
          displayName: '当前连接数',
          data: metricMap.mysql_threads_connected?.viewData || []
        },
        {
          key: 'mysql_process_list_threads_executing',
          label: '执行线程数',
          displayName: '执行线程数',
          data: metricMap.mysql_process_list_threads_executing?.viewData || []
        }
      ]),
    [metricMap.mysql_threads_connected?.viewData, metricMap.mysql_process_list_threads_executing?.viewData]
  );

  const netTrafficTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_bytes_received_rate',
          label: '接收速率',
          displayName: '接收速率',
          data: metricMap.mysql_bytes_received_rate?.viewData || []
        },
        {
          key: 'mysql_bytes_sent_rate',
          label: '发送速率',
          displayName: '发送速率',
          data: metricMap.mysql_bytes_sent_rate?.viewData || []
        }
      ]),
    [metricMap.mysql_bytes_received_rate?.viewData, metricMap.mysql_bytes_sent_rate?.viewData]
  );

  const threadSnapshot = getLatestThreadSnapshot(metricMap);
  const threadConnectedCount = hasMetricData('mysql_threads_connected') ? Math.max(threadSnapshot.connected, 0) : 0;
  const threadSleepCount = hasMetricData('mysql_process_list_threads_idle') ? Math.max(threadSnapshot.sleep, 0) : 0;
  const threadQueryCount = hasMetricData('mysql_process_list_threads_executing') ? Math.max(threadSnapshot.query, 0) : 0;
  const threadSendingCount = hasMetricData('mysql_process_list_threads_sending_data') ? Math.max(threadSnapshot.sending, 0) : 0;
  const threadLockedCount = hasMetricData('mysql_process_list_threads_waiting_for_lock') ? Math.max(threadSnapshot.locked, 0) : 0;
  const threadKnownStateCount = threadSleepCount + threadQueryCount + threadSendingCount + threadLockedCount;
  const threadDistributionTotal = Math.max(threadConnectedCount, threadKnownStateCount);
  const threadOtherValue = Math.max(
    threadDistributionTotal - threadKnownStateCount,
    0
  );
  const threadShare = [
    {
      name: 'Sleep',
      value: threadSleepCount,
      color: '#2f6bff'
    },
    {
      name: 'Query',
      value: threadQueryCount,
      color: '#27c274'
    },
    {
      name: 'Sending data',
      value: threadSendingCount,
      color: '#ffb020'
    },
    {
      name: 'Locked',
      value: threadLockedCount,
      color: '#ff5d73'
    },
    {
      name: '其他',
      value: threadOtherValue,
      color: '#b8c4d4'
    }
  ];
  const threadShareChartData = threadShare.filter((item) => item.value > 0);
  const bufferPoolUsedValue = Math.min(Math.max(bpUsedValue, 0), 100);
  const bufferPoolDirtyRatio = Math.min(Math.max(bpDirtyValue, 0), bufferPoolUsedValue);
  const bufferPoolCleanUsedRatio = Math.max(bufferPoolUsedValue - bufferPoolDirtyRatio, 0);
  const bufferPoolShareChartData = [
    { name: '已用页', value: bufferPoolCleanUsedRatio, color: '#4c8dff' },
    { name: '脏页', value: bufferPoolDirtyRatio, color: '#ff9f43' },
    { name: '空闲页', value: Math.max(100 - bufferPoolUsedValue, 0), color: '#cbd5e1' }
  ].filter((item) => item.value > 0);
  const normalizeCountValue = (value: number) => (Number.isFinite(value) ? Math.max(Math.round(value), 0) : 0);
  const bufferPoolTotalPages = normalizeCountValue(getLatest('mysql_innodb_buffer_pool_pages_total'));
  const bufferPoolFreePages = normalizeCountValue(getLatest('mysql_innodb_buffer_pool_pages_free'));
  const bufferPoolDirtyPages = normalizeCountValue(getLatest('mysql_innodb_buffer_pool_pages_dirty'));
  const bufferPoolUsedPages = Math.max(bufferPoolTotalPages - bufferPoolFreePages, 0);
  const bufferPoolBreakdown = [
    {
      name: '已用页',
      percent: bufferPoolUsedValue,
      count: bufferPoolUsedPages,
      color: '#4c8dff'
    },
    {
      name: '脏页',
      percent: bufferPoolDirtyRatio,
      count: bufferPoolDirtyPages,
      color: '#ff9f43'
    },
    {
      name: '空闲页',
      percent: Math.max(100 - bufferPoolUsedValue, 0),
      count: bufferPoolFreePages,
      color: '#cbd5e1'
    }
  ];


  const uptimeDisplay = hasMetricData('mysql_uptime') ? uptimeInsight.uptimeText : '--';
  // 运行时长卡统一样式:不画折线,只判断所选时间范围内是否发生重启(运行正常 / 期间有重启 / 状态未知)。
  const uptimeStatus = !hasMetricData('mysql_uptime')
    ? { label: '状态未知', suffix: 'Empty' as const }
    : countRestartsInRange(metricMap.mysql_uptime?.viewData || []) > 0
      ? { label: '期间有重启', suffix: 'Warning' as const }
      : { label: '运行正常', suffix: 'Success' as const };
  const connCardDisplay = getDisplayValue('mysql_connection_utilization', connDisplay);
  const qpsCardDisplay = getDisplayValue('mysql_queries_rate', qpsDisplay);
  const slowCardDisplay = getDisplayValue('mysql_slow_queries_rate', slowDisplay);
  const lockWaitRateDisplay = formatMetricValue(lockWaitRate, 'cps');
  const lockWaitRateCardDisplay = getDisplayValue('mysql_innodb_row_lock_waits_rate', lockWaitRateDisplay);
  const hasConnectionData = hasMetricData('mysql_connection_utilization');
  const hasQpsData = hasMetricData('mysql_queries_rate');
  const hasSlowData = hasMetricData('mysql_slow_queries_rate');
  const hasLockData = hasMetricData('mysql_innodb_row_lock_waits_rate');
  const hasReplicationData =
    hasMetricData('mysql_slave_seconds_behind_master') ||
    hasMetricData('mysql_slave_io_running') ||
    hasMetricData('mysql_slave_sql_running');
  const mysqlIdentity = inferMysqlIdentity({
    instanceName: resolvedInstanceName,
    hasReplicationMetrics: hasReplicationData,
    logSlaveUpdates: logSlaveUpdatesValue
  });
  const instanceMetaItems = [
    <span key="object-name" className={styles.instanceMetaInline}>{objectDisplayText}</span>,
    instanceIdText ? <span key="instance-id" className={styles.instanceMetaMuted}>{instanceIdText}</span> : null,
    <span key="identity" className={styles.instanceIdentityGroup}>
      <span className={styles.identityPill}>部署 {mysqlIdentity.deployment}</span>
      <span className={`${styles.identityPill} ${styles.identityPillRole}`}>身份 {mysqlIdentity.role}</span>
      <span className={styles.identityPill}>复制 {mysqlIdentity.replication}</span>
    </span>,
    <span key="timezone" className={styles.instanceMetaMuted}>时区 Asia/Shanghai</span>
  ].filter(Boolean) as React.ReactNode[];
  // 展示复制区块的条件:存在 SHOW SLAVE STATUS 数据(运行中或已停止的真实从库 —— hasReplicationData 是
  // 判定从库的 ground truth,主库永远没有这些行),或名称明确为从库。主库 / 独立实例两者皆不满足 → 显示"不适用"。
  // 真主库即使被临时设为只读也不会落入此分支(inferMysqlIdentity 已不再把 read_only 单独当作从库信号)。
  const replicationApplicable = hasReplicationData || mysqlIdentity.role === '从库';
  const connectionGuide = [
    { label: '连接使用率', detail: '表示当前连接数占最大连接数上限的比例。' },
    { label: '排查建议', detail: '当使用率持续升高时，需要结合连接趋势、慢查询和锁等待一起判断是否存在拥塞。' }
  ];
  const qpsGuide = [
    { label: 'QPS', detail: '每秒查询数，反映实例当前承载的查询吞吐。' },
    { label: '关联判断', detail: '通常需要结合慢查询、连接数和磁盘写入一起判断当前波动是否来自正常业务变化。' }
  ];
  const slowGuide = [
    { label: '慢查询速率', detail: '每秒慢 SQL 的新增速率。' },
    { label: '关联判断', detail: '如果慢查询升高，通常再结合锁等待、临时表和磁盘 I/O 进一步判断瓶颈位置。' }
  ];
  const lockWaitRateGuide = [
    { label: '行锁等待速率', detail: '每秒 InnoDB 行锁等待次数，过高通常表示并发写入争抢。' },
    { label: '关联判断', detail: '结合平均等待时间和慢查询一起看，判断是局部热点还是全局锁压。' }
  ];
  const qpsTrendGuide = [
    { label: 'QPS 趋势', detail: '查看查询吞吐在时间维度上的变化，用于识别波峰、波谷与突变。' },
    { label: '适用场景', detail: '适合判断业务流量波动，或与慢查询、连接数联动排查。' }
  ];
  const lockTrendGuide = [
    { label: '锁等待趋势', detail: '行锁等待速率的时序变化，用于识别锁争用的爆发与持续。' },
    { label: '适用场景', detail: '如果行锁等待上升，优先排查高并发写入热点和事务持锁时间。' }
  ];
  const threadStateGuide = [
    { label: '线程状态分布', detail: '展示当前线程停留在哪类状态，例如 Query、Sleep、Sending data、Locked。' },
    { label: '适用场景', detail: '如果 Query、Sending data 或 Locked 占比上升，说明执行链路可能存在瓶颈。' }
  ];
  const innodbTrendGuide = [
    { label: 'InnoDB 读写趋势', detail: '同时展示读 IOPS、写 IOPS 和 Redo 刷盘速率。' },
    { label: '适用场景', detail: '适合判断实例当前是读压力、写压力还是刷盘压力更明显。' }
  ];
  const bufferUsageGuide = [
    { label: '缓冲池使用情况', detail: '展示 Buffer Pool 中已用页、脏页和空闲页的占比与页数。' },
    { label: '适用场景', detail: '用于判断缓存是否接近满载，以及脏页是否积压。' }
  ];
  const replicationGuide = [
    { label: '复制状态', detail: '展示从库复制延迟，以及 IO 线程和 SQL 线程是否正常运行。' },
    { label: '适用场景', detail: '复制延迟升高时，通常要结合 Redo 刷盘、写 IOPS 和从库线程状态一起看。' }
  ];
  const connTrendGuide = [
    { label: '连接趋势', detail: '当前连接数与执行线程数的时序变化，用于识别连接堆积与执行拥塞。' },
    { label: '关联判断', detail: '连接数贴近上限且执行线程同步抬升，通常意味着出现慢请求或锁等待。' }
  ];
  const connErrorGuide = [
    { label: '连接异常', detail: '连接尝试失败、客户端异常断开、连接上限错误、内部错误的每秒速率。' },
    { label: '适用场景', detail: '任一项非零或持续升高，优先核对 max_connections、网络与客户端行为。' }
  ];
  const statementMixGuide = [
    { label: '读写语句构成', detail: 'SELECT / INSERT / UPDATE / DELETE 的每秒速率构成。' },
    { label: '适用场景', detail: '用于判断当前负载偏读还是偏写，辅助容量与索引优化方向。' }
  ];
  const netTrafficGuide = [
    { label: '网络流量', detail: 'MySQL 接收与发送字节速率。' },
    { label: '适用场景', detail: '配合 QPS 判断单请求体量，识别大结果集或批量写入。' }
  ];
  const tempCacheGuide = [
    { label: '临时表与缓存压力', detail: '磁盘临时表、表缓存未命中、打开表速率的每秒速率;非零或升高即额外开销信号。' },
    { label: '适用场景', detail: '磁盘临时表升高优先优化 SQL/内存阈值;表缓存未命中升高考虑增大 table_open_cache。' }
  ];
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

  const goBack = () => {
    router.push('/monitor/view');
  };

  const onInstanceChange = (value: string) => {
    const target = instanceOptions.find((item) => item.value === value);
    const params = new URLSearchParams(searchParams.toString());
    params.set('instance_id', value);
    params.set('instance_name', String(target?.label || value));
    params.set('instance_id_values', (target?.instanceIdValues || [value]).join(','));
    router.push(`/monitor/view/dashboard/mysql?${params.toString()}`);
  };

  const getNoDataType = (...metricNames: string[]): 'empty' | 'error' => {
    if (metricNames.includes('mysql_collection_status')) {
      return collectionStatusMetric?.loadState === 'error' ? 'error' : 'empty';
    }

    const targets = metricNames.map((name) => metricMap[name]).filter(Boolean);
    return targets.length > 0 && targets.every((metric) => metric?.loadState === 'error') ? 'error' : 'empty';
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
            frequencyList={MYSQL_REFRESH_FREQUENCY_LIST}
            onTimeChange={onTimeChange}
            onFrequenceChange={onFrequenceChange}
            onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
            onBack={goBack}
            showTimeSelector={false}
            styles={styles}
          />

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
              onRefresh: () => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))
            }}
            styles={styles}
          />
        </div>

        <div>
          {showEmpty ? (
            <div className={styles.empty}>
              <Empty description={t('common.noData')} />
            </div>
          ) : (
            <>
              {displayMode === 'dashboard' ? (
                <div className={styles.modeContent}>
                  <div className={styles.primaryGrid}>
                    <CollectionStatusCard
                      styles={styles}
                      status={statusInfo}
                      timeline={collectionStatusTimeline}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="运行时长" items={[{ label: '运行时长', detail: 'MySQL 实例自上次启动后的持续运行时间，反映服务稳定性；期间发生重启会重新计时。' }]} />}
                      value={uptimeDisplay}
                      unit=""
                      icon={<ClockCircleOutlined />}
                      iconStyle={{ background: 'rgba(91, 143, 249, 0.12)', color: '#5b8ff9' }}
                      color="#5b8ff9"
                      footer={<span>{hasMetricData('mysql_uptime') ? `启动 ${uptimeInsight.startupTimeText}` : metricEmptyText}</span>}
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
                      noDataType={getNoDataType('mysql_uptime')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="连接使用率" items={connectionGuide} />}
                      value={connCardDisplay.value}
                      unit={connCardDisplay.unit}
                      icon={<NodeIndexOutlined />}
                      iconStyle={{ background: 'rgba(255, 145, 20, 0.12)', color: '#ff8a1f' }}
                      color="#ff7a00"
                      compare={hasConnectionData ? connCompare : null}
                      footer={<><span>{hasConnectionData ? `当前 ${threadsConnectedValue.toFixed(0)} / 上限 ${maxConnectionsValue.toFixed(0)}` : metricEmptyText}</span></>}
                      trendData={metricMap.mysql_connection_utilization?.viewData || []}
                      noDataType={getNoDataType('mysql_connection_utilization')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="慢查询速率" items={slowGuide} />}
                      value={slowCardDisplay.value}
                      unit={slowCardDisplay.unit}
                      icon={<ClockCircleOutlined />}
                      iconStyle={{ background: 'rgba(255, 77, 79, 0.12)', color: '#ff4d4f' }}
                      color="#ff3030"
                      compare={hasSlowData ? slowCompare : null}
                      footer={<><span>{hasSlowData && hasLockData ? `行锁等待 ${formatPerMinute(lockWaitRate * 60)}` : metricEmptyText}</span></>}
                      trendData={metricMap.mysql_slow_queries_rate?.viewData || []}
                      noDataType={getNoDataType('mysql_slow_queries_rate')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="行锁等待速率" items={lockWaitRateGuide} />}
                      value={lockWaitRateCardDisplay.value}
                      unit={lockWaitRateCardDisplay.unit}
                      icon={<NodeIndexOutlined />}
                      iconStyle={{ background: 'rgba(255, 77, 79, 0.08)', color: '#ff4d4f' }}
                      color="#ff4d4f"
                      compare={hasLockData ? lockWaitRateCompare : null}
                      footer={<><span>{hasLockData ? `平均等待 ${lockWait.toFixed(lockWait >= 10 ? 0 : 1)} ms` : metricEmptyText}</span></>}
                      trendData={metricMap.mysql_innodb_row_lock_waits_rate?.viewData || []}
                      noDataType={getNoDataType('mysql_innodb_row_lock_waits_rate')}
                    />
                    <StatCard
                      styles={styles}
                      title={<TitleWithGuide styles={styles} title="QPS（每秒查询数）" items={qpsGuide} />}
                      value={qpsCardDisplay.value}
                      unit={qpsCardDisplay.unit}
                      icon={<ThunderboltOutlined />}
                      iconStyle={{ background: 'rgba(47, 107, 255, 0.12)', color: '#2f6bff' }}
                      color="#2f6bff"
                      compare={hasQpsData ? qpsCompare : null}
                      footer={<><span>{hasQpsData ? `SELECT 查询 ${selectValue.toFixed(1)}/s` : metricEmptyText}</span></>}
                      trendData={metricMap.mysql_queries_rate?.viewData || []}
                      noDataType={getNoDataType('mysql_queries_rate')}
                    />
                  </div>

                  {/* 分区 1 · 连接与线程压力 */}
                  <div className={styles.sectionLabel}>连接与线程压力</div>
                  <section className={styles.dashboardSection}>
                    <div className={styles.sectionGrid}>
                      <TrendChartPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="连接趋势" items={connTrendGuide} className={styles.panelTitleWithGuide} />}
                        legends={TREND_LEGENDS.connection}
                        data={connTrendData}
                        metric={buildMetricItem(metricMap.mysql_threads_connected || dashboardMetrics[0])}
                        unit="counts"
                        seriesStyles={TREND_LEGENDS.connection.map((item) => ({
                          color: item.color,
                          fillOpacity: item.primary ? 0.08 : 0.03,
                          strokeOpacity: item.primary ? 1 : 0.7,
                          strokeWidth: item.primary ? 2.8 : 2.1,
                          unit: 'counts'
                        }))}
                        onXRangeChange={onXRangeChange}
                      />
                      <RingChartPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="线程状态分布" items={threadStateGuide} className={styles.panelTitleWithGuide} />}
                        data={threadShareChartData}
                        centerValue={threadDistributionTotal.toFixed(0)}
                        centerCaption="当前总数"
                        isEmpty={threadShareChartData.length === 0}
                        emptyDescription="暂无线程状态数据"
                      />
                      <HorizontalBarPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="连接异常" items={connErrorGuide} className={styles.panelTitleWithGuide} />}
                        items={[
                          { label: '连接尝试失败', value: abortedConnectsRate * 60, display: formatPerMinute(abortedConnectsRate * 60), color: '#a855f7', max: Math.max(abortedConnectsRate * 60, 1), trend: metricMap.mysql_aborted_connects_rate?.viewData || [] },
                          { label: '客户端异常断开', value: abortedClientsRate * 60, display: formatPerMinute(abortedClientsRate * 60), color: '#52c41a', max: Math.max(abortedClientsRate * 60, 1), trend: metricMap.mysql_aborted_clients_rate?.viewData || [] },
                          { label: '连接上限错误', value: maxConnectionErrorsRate * 60, display: formatPerMinute(maxConnectionErrorsRate * 60), color: '#ff4d4f', max: Math.max(maxConnectionErrorsRate * 60, 1), trend: metricMap.mysql_connection_errors_max_connections_rate?.viewData || [] },
                          { label: '内部连接错误', value: internalConnectionErrors, display: internalConnectionErrors.toFixed(0), color: '#faad14', max: Math.max(internalConnectionErrors, 1), trend: metricMap.mysql_connection_errors_internal?.viewData || [] }
                        ]}
                      />
                    </div>
                  </section>

                  {/* 分区 2 · 查询吞吐 */}
                  <div className={styles.sectionLabel}>查询吞吐</div>
                  <section className={styles.dashboardSection}>
                    <div className={styles.sectionGrid}>
                      <TrendChartPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="QPS 趋势" items={qpsTrendGuide} className={styles.panelTitleWithGuide} />}
                        legends={TREND_LEGENDS.qps}
                        data={qpsTrendData}
                        metric={buildMetricItem(metricMap.mysql_queries_rate || dashboardMetrics[0])}
                        unit="cps"
                        seriesStyles={TREND_LEGENDS.qps.map((item) => ({ color: item.color, fillOpacity: item.primary ? 0.09 : 0.03, strokeOpacity: item.primary ? 1 : 0.72, strokeWidth: item.primary ? 2.8 : 2.1, unit: 'cps' }))}
                        onXRangeChange={onXRangeChange}
                      />
                      <HorizontalBarPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="读写语句构成" items={statementMixGuide} className={styles.panelTitleWithGuide} />}
                        items={[
                          { label: 'SELECT', value: selectValue, display: `${selectValue.toFixed(1)}/s`, color: '#2f6bff', max: Math.max(selectValue, insertValue, updateValue, deleteValue, 1), trend: metricMap.mysql_com_select_rate?.viewData || [] },
                          { label: 'INSERT', value: insertValue, display: `${insertValue.toFixed(1)}/s`, color: '#ff9f43', max: Math.max(selectValue, insertValue, updateValue, deleteValue, 1), trend: metricMap.mysql_com_insert_rate?.viewData || [] },
                          { label: 'UPDATE', value: updateValue, display: `${updateValue.toFixed(1)}/s`, color: '#faad14', max: Math.max(selectValue, insertValue, updateValue, deleteValue, 1), trend: metricMap.mysql_com_update_rate?.viewData || [] },
                          { label: 'DELETE', value: deleteValue, display: `${deleteValue.toFixed(1)}/s`, color: '#ff7875', max: Math.max(selectValue, insertValue, updateValue, deleteValue, 1), trend: metricMap.mysql_com_delete_rate?.viewData || [] }
                        ]}
                      />
                      <TrendChartPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="网络流量" items={netTrafficGuide} className={styles.panelTitleWithGuide} />}
                        legends={TREND_LEGENDS.network}
                        data={netTrafficTrendData}
                        metric={buildMetricItem(metricMap.mysql_bytes_received_rate || dashboardMetrics[0])}
                        unit="byteps"
                        seriesStyles={TREND_LEGENDS.network.map((item) => ({ color: item.color, fillOpacity: item.primary ? 0.08 : 0.03, strokeOpacity: item.primary ? 1 : 0.7, strokeWidth: item.primary ? 2.8 : 2.1, unit: 'byteps' }))}
                        onXRangeChange={onXRangeChange}
                      />
                    </div>
                  </section>

                  {/* 分区 3 · 锁等待 */}
                  <div className={styles.sectionLabel}>锁等待</div>
                  <section className={styles.dashboardSection}>
                    <div className={styles.sectionGrid}>
                      <TrendChartPanel
                        styles={styles}
                        className={styles.span8}
                        title={<TitleWithGuide styles={styles} title="锁等待趋势" items={lockTrendGuide} className={styles.panelTitleWithGuide} />}
                        subtitle="行锁等待速率"
                        legends={TREND_LEGENDS.lockWaits}
                        data={lockWaitTrendData}
                        metric={buildMetricItem(metricMap.mysql_innodb_row_lock_waits_rate || dashboardMetrics[0])}
                        unit="cps"
                        seriesStyles={TREND_LEGENDS.lockWaits.map((item) => ({ color: item.color, fillOpacity: 0.08, strokeOpacity: 1, strokeWidth: 2.8, unit: 'cps' }))}
                        onXRangeChange={onXRangeChange}
                      />
                      <StatCard
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="平均行锁等待" items={lockWaitRateGuide} />}
                        value={renderMetricValue('mysql_innodb_row_lock_time_avg', lockWait.toFixed(lockWait >= 10 ? 0 : 1))}
                        unit={hasMetricData('mysql_innodb_row_lock_time_avg') ? 'ms' : ''}
                        icon={<ClockCircleOutlined />}
                        iconStyle={{ background: 'rgba(255, 77, 79, 0.08)', color: '#ff4d4f' }}
                        color="#ff4d4f"
                        compare={null}
                        footer={<><span>{hasLockData ? `行锁等待 ${formatPerMinute(lockWaitRate * 60)}` : metricEmptyText}</span></>}
                        trendData={metricMap.mysql_innodb_row_lock_time_avg?.viewData || []}
                        noDataType={getNoDataType('mysql_innodb_row_lock_time_avg')}
                      />
                    </div>
                  </section>

                  {/* 分区 4 · InnoDB 缓冲池 */}
                  <div className={styles.sectionLabel}>InnoDB 缓冲池</div>
                  <section className={styles.dashboardSection}>
                    <div className={styles.sectionGrid}>
                      <RingChartPanel
                        styles={styles}
                        className={`${styles.span4} ${styles.fillPanel}`}
                        ringCardClassName={`${styles.bufferPoolRingCard} ${styles.ringCardRelaxed}`}
                        ringChartWrapClassName={styles.bufferPoolChartWrap}
                        title={<TitleWithGuide styles={styles} title="缓冲池使用" items={bufferUsageGuide} className={styles.panelTitleWithGuide} />}
                        subtitle="已用、脏页与空闲页"
                        data={bufferPoolShareChartData}
                        centerValue={bufferPoolUsedValue.toFixed(0)}
                        centerCaption="使用率"
                        isEmpty={!hasMetricData('mysql_buffer_pool_used_ratio')}
                        emptyDescription="暂无缓冲池数据"
                        infoRows={bufferPoolBreakdown.map((item) => ({
                          name: item.name,
                          color: item.color,
                          primary: `${item.percent.toFixed(1)}%`,
                          secondary: `(${item.count.toLocaleString()})`
                        }))}
                      />
                      <TrendChartPanel
                        styles={styles}
                        className={`${styles.span8} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="InnoDB 读写趋势" items={innodbTrendGuide} className={styles.panelTitleWithGuide} />}
                        subtitle="读写与 Redo 刷盘"
                        legends={TREND_LEGENDS.innodb}
                        data={innodbTrendData}
                        metric={buildMetricItem(metricMap.mysql_innodb_data_reads_rate || dashboardMetrics[0])}
                        unit="cps"
                        seriesStyles={TREND_LEGENDS.innodb.map((item) => ({ color: item.color, fillOpacity: item.primary ? 0.08 : 0.03, strokeOpacity: item.primary ? 1 : 0.68, strokeWidth: item.primary ? 2.8 : 2.1 }))}
                        bodyBottom={(
                          <div className={styles.inlineStats}>
                            <div className={styles.inlineStat}><span>读 IOPS</span><strong>{dataReadValue.toFixed(1)}/s</strong></div>
                            <div className={styles.inlineStat}><span>写 IOPS</span><strong>{dataWriteValue.toFixed(1)}/s</strong></div>
                            <div className={styles.inlineStat}><span>Redo 刷盘</span><strong>{fsyncValue.toFixed(1)}/s</strong></div>
                          </div>
                        )}
                        onXRangeChange={onXRangeChange}
                      />
                    </div>
                  </section>

                  {/* 分区 5 · 临时表与复制状态(复制部分仅主从) */}
                  <div className={styles.sectionLabel}>临时表与复制状态</div>
                  <section className={styles.dashboardSection}>
                    <div className={styles.sectionGrid}>
                      <HorizontalBarPanel
                        styles={styles}
                        className={`${replicationApplicable ? styles.span4 : styles.span8} ${styles.fillPanel}`}
                        title={<TitleWithGuide styles={styles} title="临时表与缓存压力" items={tempCacheGuide} className={styles.panelTitleWithGuide} />}
                        items={[
                          { label: '磁盘临时表速率', value: tmpDiskRate * 60, display: formatPerMinute(tmpDiskRate * 60), color: '#ff4d4f', max: Math.max(tmpTotalRate * 60, 1), trend: metricMap.mysql_created_tmp_disk_tables_rate?.viewData || [] },
                          { label: '表缓存未命中', value: tableCacheMissRate * 60, display: formatPerMinute(tableCacheMissRate * 60), color: '#faad14', max: Math.max((tableCacheMissRate + openedTablesRate) * 60, 1), trend: metricMap.mysql_table_open_cache_misses_rate?.viewData || [] },
                          { label: '打开表速率', value: openedTablesRate * 60, display: formatPerMinute(openedTablesRate * 60), color: '#2f6bff', max: Math.max(openedTablesRate * 60, 1), trend: metricMap.mysql_opened_tables_rate?.viewData || [] }
                        ]}
                      />
                      {replicationApplicable ? (
                        <>
                          <TrendChartPanel
                            styles={styles}
                            className={`${styles.span4} ${styles.fillPanel}`}
                            title={<TitleWithGuide styles={styles} title="复制延迟趋势" items={replicationGuide} className={styles.panelTitleWithGuide} />}
                            subtitle="从库落后主库秒数"
                            legends={TREND_LEGENDS.replication}
                            data={replicationTrendData}
                            metric={buildMetricItem(metricMap.mysql_slave_seconds_behind_master || dashboardMetrics[0])}
                            unit="s"
                            seriesStyles={TREND_LEGENDS.replication.map((item) => ({ color: item.color, fillOpacity: 0.08, strokeOpacity: 1, strokeWidth: 2.8, unit: 's' }))}
                            onXRangeChange={onXRangeChange}
                          />
                          <DashboardPanel
                            styles={styles}
                            className={`${styles.span4} ${styles.fillPanel}`}
                            bodyClassName={styles.fillBody}
                            title="复制线程与配置"
                            guide={replicationGuide}
                          >
                            <div className={styles.replicationKvList}>
                              <div className={styles.replicationKvRow}>
                                <span className={styles.replicationKvLabel}>IO 线程</span>
                                <Tag className={styles.replicationStatusTag} color={replicationIoRunning > 0 ? 'success' : 'error'}>
                                  {replicationIoRunning > 0 ? '运行中' : '已停止'}
                                </Tag>
                              </div>
                              <div className={styles.replicationKvRow}>
                                <span className={styles.replicationKvLabel}>SQL 线程</span>
                                <Tag className={styles.replicationStatusTag} color={replicationSqlRunning > 0 ? 'success' : 'error'}>
                                  {replicationSqlRunning > 0 ? '运行中' : '已停止'}
                                </Tag>
                              </div>
                              <div className={styles.replicationKvRow}>
                                <span className={styles.replicationKvLabel}>binlog</span>
                                <Tag className={styles.replicationStatusTag} color={logBinValue > 0 ? 'success' : 'default'}>
                                  {logBinValue > 0 ? '已开启' : '未开启'}
                                </Tag>
                              </div>
                              <div className={styles.replicationKvRow}>
                                <span className={styles.replicationKvLabel}>回放写日志</span>
                                <Tag className={styles.replicationStatusTag} color={logSlaveUpdatesValue > 0 ? 'success' : 'default'}>
                                  {logSlaveUpdatesValue > 0 ? '已记录' : '未记录'}
                                </Tag>
                              </div>
                            </div>
                          </DashboardPanel>
                        </>
                      ) : (
                        <DashboardPanel
                          styles={styles}
                          className={`${styles.span4} ${styles.fillPanel}`}
                          bodyClassName={`${styles.replicationStandalone} ${styles.fillBody}`}
                          title="复制状态"
                          subtitle={`${mysqlIdentity.deployment}实例无需复制线程`}
                          guide={replicationGuide}
                        >
                          <div className={styles.replicationRoleBadge}>{mysqlIdentity.role}</div>
                          <div className={styles.replicationStandaloneTitle}>无需复制线程</div>
                          <div className={styles.replicationStandaloneDesc}>
                            当前实例为{mysqlIdentity.deployment}的{mysqlIdentity.role}，不需要展示从库复制延迟与 SQL/IO 线程状态。
                          </div>
                          <div className={styles.replicationStandaloneTags}>
                            <Tag className={styles.replicationStatusTag}>IO 不适用</Tag>
                            <Tag className={styles.replicationStatusTag}>SQL 不适用</Tag>
                          </div>
                        </DashboardPanel>
                      )}
                    </div>
                  </section>
                </div>
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
