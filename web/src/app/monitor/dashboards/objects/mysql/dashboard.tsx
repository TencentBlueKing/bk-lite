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
  useLoadSequence
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
import { readMysqlHeaderIdentity, readMysqlProHeader } from './layered/ia';
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

export default function MysqlDashboardPage() {
  const { getInstanceQuery } = useViewApi();
  const { getInstanceList } = useMonitorApi();
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const loadSequence = useLoadSequence();
  const modeQuery = searchParams.toString();
  const [loading, setLoading] = useState(true);
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
  const [instanceOptions, setInstanceOptions] = useState<MysqlInstanceOption[]>([]);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [metricsRefreshSignal, setMetricsRefreshSignal] = useState(0);

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
          setCollectionStatusMetric(null);
          if (!silent) setLoading(false);
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

  const pageTitle = displayMode === 'metrics'
    ? `${objectDisplayText} 全量指标`
    : displayMode === 'category'
      ? 'MySQL 实例详情'
      : 'MySQL 监控仪表盘';
  const hasDashboardContent = dashboardMetrics.length > 0;
  const showEmpty = isDashboardMode ? !hasDashboardContent : false;

  const chrome = displayMode === 'category' ? hostChrome : styles;
  const mysqlIdentity = readMysqlHeaderIdentity(metricMap, resolvedInstanceName);
  const proHeader = displayMode === 'category' ? readMysqlProHeader(metricMap) : null;
  // 实例 ID 与展示名仅分隔符不同时（mysql_3306 vs mysql-3306）视为重复，不再展示。
  const normalizeIdentityKey = (value: string) => value.trim().toLowerCase().replace(/[-_\s]+/g, '');
  const showInstanceId =
    Boolean(instanceIdText) &&
    normalizeIdentityKey(instanceIdText) !== normalizeIdentityKey(primaryInstanceText);
  const identityMetaItems = proHeader
    ? [
      <span key="role" className={`${styles.identityPill} ${styles.identityPillRole}`}>
        {proHeader.pill}
      </span>,
      proHeader.aside ? (
        <span key="aside" className={styles.instanceMetaMuted}>
          {proHeader.aside}
        </span>
      ) : null,
      proHeader.binlog ? (
        <span key="binlog" className={styles.identityPill}>
          {proHeader.binlog}
        </span>
      ) : null
    ].filter(Boolean)
    : mysqlIdentity.deployment === '单节点'
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
  const instanceMetaItems = [
    <span key="object-name" className={chrome.instanceMetaInline}>
      {objectDisplayText}
    </span>,
    showInstanceId ? (
      <span key="instance-id" className={chrome.instanceMetaMuted}>
        {instanceIdText}
      </span>
    ) : null,
    ...identityMetaItems,
    <span key="timezone" className={chrome.instanceMetaMuted}>
      时区 Asia/Shanghai
    </span>
  ].filter(Boolean) as React.ReactNode[];
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
    <div className={chrome.page} data-mysql-chrome={displayMode === 'category' ? 'host' : 'classic'}>
      <div className={chrome.shell}>
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
            onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
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
              onRefresh: () => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))
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
                    metricMap={metricMap}
                    previousMetricMap={previousMetricMap}
                    loading={loading}
                    instanceId={String(instanceId || '')}
                    monitorObjectId={monitorObjectId}
                    nodeId={currentInstanceOption?.nodeId || ''}
                    ip={currentInstanceOption?.ip || ''}
                    timeValues={timeValues}
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
