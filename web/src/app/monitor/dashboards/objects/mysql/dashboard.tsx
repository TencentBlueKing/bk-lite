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
import { DASHBOARD_METRICS } from './config';
import { MetricSeries, MysqlMetricConfig } from './types';
import styles from './index.module.scss';
import useMonitorApi from '@/app/monitor/api';
import {
  DEFAULT_REFRESH_FREQUENCY_LIST,
  fetchDashboardInstancePages,
  buildSearchParams,
  getLatestChartValue,
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
  freezeTimeValues,
  toMetricSeries,
  useLoadSequence
} from '../../shared/utils';
import {
  DashboardPageHeader,
  DashboardInstanceCard,
  DashboardPanel
} from '../../shared/widgets';
import MysqlProLayout from './layered/mysql-pro-layout';

interface MysqlInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
  interval?: number;
  nodeId?: string;
  ip?: string;
}

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

export default function MysqlDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const loadSequence = useLoadSequence();
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
  const [instanceOptions, setInstanceOptions] = useState<MysqlInstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);

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
        }
      }
    };

    loadInstances();

    return () => {
      active = false;
    };
  }, [monitorObjectId]);

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

  const loadMetricGroup = async (metricNames: readonly string[], targetTimeValues: TimeValuesProps) => {
    const metrics = metricNames
      .map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name))
      .filter((metric): metric is MysqlMetricConfig => Boolean(metric));

    return runWithConcurrency(
      metrics,
      METRIC_QUERY_CONCURRENCY,
      async (metric) =>
        getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, targetTimeValues, undefined, false, currentInstanceInterval, {
          monitorObjectId,
          instanceId,
        }))
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
        if (!idValues.length) {
          setSeries({});
          setPreviousSeries({});
          if (!silent) setLoading(false);
          return;
        }
        const frozenTimeValues = freezeTimeValues(timeValues);
        const previousTimeValues = buildPreviousPeriodTimeValues(frozenTimeValues);
        const compareMetrics = MYSQL_COMPARE_METRICS.map((name) => MYSQL_METRIC_CONFIG_BY_NAME.get(name)).filter(
          (metric): metric is MysqlMetricConfig => Boolean(metric)
        );
        const summaryResultsPromise = loadMetricGroup(MYSQL_METRIC_GROUPS[0].names, frozenTimeValues);

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

        const summaryResults = await summaryResultsPromise;

        if (!loadSequence.isCurrent(loadSeq)) {
          return;
        }

        setSeries((prev) => (silent ? { ...prev, ...Object.fromEntries(summaryResults) } : Object.fromEntries(summaryResults)));

        if (!silent) {
          setLoading(false);
        }

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

  const hasMetricData = (name: string) => {
    const target = metricMap[name];
    return target?.loadState === 'success' && Array.isArray(target.viewData) && target.viewData.length > 0;
  };

  const logSlaveUpdatesValue = getLatest('mysql_variables_log_slave_updates');
  const hasReplicationData =
    hasMetricData('mysql_slave_seconds_behind_master') ||
    hasMetricData('mysql_slave_io_running') ||
    hasMetricData('mysql_slave_sql_running');
  const mysqlIdentity = inferMysqlIdentity({
    instanceName: resolvedInstanceName,
    hasReplicationMetrics: hasReplicationData,
    logSlaveUpdates: logSlaveUpdatesValue
  });
  const normalizeIdentityKey = (value: string) => value.trim().toLowerCase().replace(/[-_\s]+/g, '');
  const showInstanceId =
    Boolean(instanceIdText) &&
    normalizeIdentityKey(instanceIdText) !== normalizeIdentityKey(primaryInstanceText);
  const identityMetaItems =
    mysqlIdentity.deployment === '单节点'
      ? [
        <span key="topology" className={styles.instanceMetaInline}>
          单节点
        </span>
      ]
      : [
        <span key="topology" className={styles.instanceMetaInline}>
          主从复制
        </span>,
        <span key="role" className={`${styles.identityPill} ${styles.identityPillRole}`}>
          {mysqlIdentity.role}
        </span>
      ];
  const instanceMetaItems = [
    <span key="object-name" className={styles.instanceMetaInline}>
      {objectDisplayText}
    </span>,
    <span key="fleet" className={styles.instanceMetaMuted}>
      数据库实例
    </span>,
    showInstanceId ? (
      <span key="instance-id" className={styles.instanceMetaMuted}>
        {instanceIdText}
      </span>
    ) : null,
    ...identityMetaItems,
    <span key="timezone" className={styles.instanceMetaMuted}>
      时区 Asia/Shanghai
    </span>
  ].filter(Boolean) as React.ReactNode[];
  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : 'MySQL 实例详情';
  const hasDashboardContent = dashboardMetrics.length > 0;
  const showEmpty = isDashboardMode ? !hasDashboardContent : false;

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

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.unifiedShell} data-dashboard-shell="unified">
          <div className={styles.pageIntro}>
          <DashboardPageHeader
            title={pageTitle}
            displayMode={displayMode}
            onDisplayModeChange={setDisplayMode}
            timeDefaultValue={timeDefaultValue}
            frequencyList={MYSQL_REFRESH_FREQUENCY_LIST}
            onTimeChange={onTimeChange}
            onFrequenceChange={onFrequenceChange}
            onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
            showTimeSelector={false}
            styles={styles}
          />
          </div>
          <div className={styles.unifiedHostBar}>
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
        </div>

        <div className={styles.unifiedBelow}>
          {showEmpty ? (
            <div className={styles.empty}>
              <CompactEmptyState description={t('common.noData')} />
            </div>
          ) : (
            <>
              {displayMode === 'dashboard' ? (
                <div className={styles.modeContent}>
                  <MysqlProLayout
                    metricMap={metricMap}
                    previousMetricMap={previousMetricMap}
                    loading={loading}
                    instanceId={String(instanceId || '')}
                    nodeId={currentInstanceOption?.nodeId || ''}
                    ip={currentInstanceOption?.ip || ''}
                    timeValues={timeValues}
                    minStepSeconds={currentInstanceInterval}
                  />
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
