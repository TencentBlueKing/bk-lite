'use client';

import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Button, Empty, Segmented, Spin, Tag, Tooltip } from 'antd';
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  RiseOutlined,
  FallOutlined,
  ApiOutlined,
  FieldTimeOutlined,
  HddOutlined,
  NodeIndexOutlined,
  AppstoreOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import { Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import TimeSelector from '@/components/time-selector';
import LineChart from '@/app/monitor/components/charts/lineChart';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import { useTranslation } from '@/utils/i18n';
import {
  calculateMetrics,
  getRecentTimeRange,
  mergeViewQueryKeyValues,
  renderChart
} from '@/app/monitor/utils/common';
import { ChartData, MetricItem, TimeSelectorDefaultValue, TimeValuesProps } from '@/app/monitor/types';
import { SearchParams } from '@/app/monitor/types/search';
import {
  DASHBOARD_METRICS,
  MYSQL_COLLECTION_STATUS_QUERY,
  TREND_LEGENDS
} from './config';
import { MetricSeries, MetricUnit } from './types';
import styles from './index.module.scss';

const MAX_POINTS = 100;
const DEFAULT_STEP = 360;

const formatMetricValue = (value: number, unit: MetricUnit) => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  if (unit === 'percent') {
    return { value: value.toFixed(1), unit: '%' };
  }

  if (unit === 'ms') {
    return { value: value.toFixed(1), unit: 'ms' };
  }

  if (unit === 'cps') {
    return { value: value >= 100 ? value.toFixed(0) : value.toFixed(2), unit: '/s' };
  }

  if (unit === 'permin') {
    return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: '/min' };
  }

  if (unit === 'byteps') {
    const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    let next = value;
    let idx = 0;
    while (next >= 1024 && idx < units.length - 1) {
      next /= 1024;
      idx += 1;
    }
    return { value: next >= 100 ? next.toFixed(0) : next.toFixed(1), unit: units[idx] };
  }

  if (unit === 'bytes') {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let next = value;
    let idx = 0;
    while (next >= 1024 && idx < units.length - 1) {
      next /= 1024;
      idx += 1;
    }
    return { value: next >= 100 ? next.toFixed(0) : next.toFixed(1), unit: units[idx] };
  }

  return {
    value: value >= 1000 ? value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : value.toFixed(value >= 100 ? 0 : 1),
    unit: unit === 'ops' ? '/s' : ''
  };
};

const buildSearchParams = (
  query: string,
  source_unit: string,
  idValues: string[],
  instanceIdKeys: string[],
  timeValues: TimeValuesProps
): SearchParams => {
  const effectiveIdValues = idValues.length ? idValues : [''];
  const labels = mergeViewQueryKeyValues([
    { keys: instanceIdKeys.length ? instanceIdKeys : ['instance_id'], values: effectiveIdValues }
  ]);
  const recentTimeRange = getRecentTimeRange(timeValues);
  const startTime = recentTimeRange.at(0);
  const endTime = recentTimeRange.at(1);
  const params: SearchParams = {
    query: query.replace(/__\$labels__/g, labels),
    source_unit
  };

  if (startTime && endTime) {
    params.start = startTime;
    params.end = endTime;
    params.step = Math.max(
      Math.ceil((params.end / MAX_POINTS - params.start / MAX_POINTS) / DEFAULT_STEP),
      1
    );
  }

  return params;
};

const getLatestChartValue = (data: ChartData[]) => {
  const latestValue = calculateMetrics(data as Record<string, number>[]).latestValue;
  return typeof latestValue === 'number' ? latestValue : 0;
};

const normalizeDisplayText = (value?: string | null) => {
  if (!value) {
    return '';
  }

  const trimmed = value.trim();
  if (!trimmed || trimmed === '--') {
    return '';
  }

  const withoutQuotes = trimmed.replace(/^["'`\[(\s]+|["'`\])\s]+$/g, '').trim();
  if (!withoutQuotes || withoutQuotes === '--') {
    return '';
  }

  if (/^[A-Za-z0-9+/=,_-]{12,}$/.test(withoutQuotes) && !/[.:]/.test(withoutQuotes)) {
    return '';
  }

  return withoutQuotes;
};

const parseLegacyParamList = (value?: string | null) => {
  if (!value) {
    return [] as string[];
  }

  const normalized = value
    .replace(/[()\[\]'"`]/g, '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  return Array.from(new Set(normalized));
};

const inferMysqlRole = (roleSignals: {
  readOnly: number;
  superReadOnly: number;
  logBin: number;
  logSlaveUpdates: number;
}) => {
  const { readOnly, superReadOnly, logBin, logSlaveUpdates } = roleSignals;

  if (readOnly > 0 || superReadOnly > 0 || logSlaveUpdates > 0) {
    return '从库';
  }

  if (logBin > 0) {
    return '主库';
  }

  return '单点';
};

const toMetricSeries = (
  metric: MysqlMetricConfig,
  result: any,
  instanceId: React.Key,
  instanceName: string,
  idValues: string[],
  instanceIdKeys: string[]
) => {
  const viewData = renderChart(result?.data?.result || [], [
    {
      instance_id_values: idValues,
      instance_name: instanceName,
      instance_id: String(instanceId || ''),
      instance_id_keys: instanceIdKeys,
      dimensions: metric.dimensions || [],
      title: metric.display_name
    }
  ]);

  return {
    ...metric,
    viewData,
    loadState: 'success' as const
  };
};

const buildMetricItem = (metric: MetricSeries): MetricItem => ({
  id: 0,
  metric_group: 0,
  metric_object: 0,
  name: metric.name,
  type: 'number',
  display_name: metric.display_name,
  dimensions: [],
  dimensions: metric.dimensions || [],
  unit: metric.unit,
  query: metric.query,
  description: metric.description,
  color: metric.color,
  viewData: metric.viewData
});

const mergeChartSeries = (
  seriesList: Array<{ key: string; label: string; displayName?: string; data: ChartData[] }>
): ChartData[] => {
  const merged = new Map<number, ChartData>();

  seriesList.forEach((series, index) => {
    const valueKey = `value${index + 1}`;

    series.data.forEach((point) => {
      const time = Number(point.time);
      const current = merged.get(time) || {
        time,
        title: series.label,
        details: {}
      };

      current[valueKey] = Number(point.value1 ?? 0);
      current.details = current.details || {};
      current.details[valueKey] = [
        {
          name: series.key,
          label: '',
          displayName: series.displayName,
          value: series.displayName || series.label
        }
      ];

      merged.set(time, current);
    });
  });

  return Array.from(merged.values()).sort((a, b) => Number(a.time) - Number(b.time));
};

const getCollectionStatus = (metric?: MetricSeries | null) => {
  const hasData = Array.isArray(metric?.viewData) && metric.viewData.length > 0;
  const hasError = metric?.loadState === 'error';

  if (hasData) {
    return {
      label: '采集正常',
      tagColor: 'success' as const,
      accentColor: '#27c274',
      summary: '监控探针正在正常采集',
      detail: '当前采集状态指标可正常返回，说明 MySQL 监控探针采集链路正常。'
    };
  }

  if (hasError) {
    return {
      label: '采集异常',
      tagColor: 'error' as const,
      accentColor: '#ff4d4f',
      summary: '采集状态查询失败',
      detail: '当前采集状态指标查询失败，请检查探针与数据库连通性或采集配置。'
    };
  }

  return {
    label: '暂无数据',
    tagColor: 'warning' as const,
    accentColor: '#fa8c16',
    summary: '当前时间范围内无采集数据',
    detail: '尚未在当前时间范围内看到采集状态数据，请检查时间范围或等待新数据进入。'
  };
};

const MiniTrendChart = ({ data, color }: { data: ChartData[]; color: string }) => {
  const gradientId = useId().replace(/:/g, '_');
  const chartData = useMemo(
    () =>
      data
        .map((point) => ({
          time: Number(point.time),
          value: Number(point.value1 ?? 0)
        }))
        .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value)),
    [data]
  );

  if (!chartData.length) {
    return <div className={styles.miniTrendPlaceholder} />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.24} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
};

const StatCard = ({
  title,
  value,
  unit,
  icon,
  iconStyle,
  color,
  footer,
  trendData,
  noDataType = 'empty'
}: {
  title: string;
  value: string;
  unit: string;
  icon: React.ReactNode;
  iconStyle: React.CSSProperties;
  color: string;
  footer: React.ReactNode;
  trendData: ChartData[];
  noDataType?: 'empty' | 'error';
}) => {
  return (
    <div className={styles.statCard}>
      <div className={styles.statHeader}>
        <div className={styles.statLabel}>{title}</div>
        <div className={styles.statIcon} style={iconStyle}>
          {icon}
        </div>
      </div>
      <div className={styles.statBody}>
        <div className={styles.statValue} style={{ color }}>
          {value}
          {unit ? <span className={styles.statUnit}>{unit}</span> : null}
        </div>
        <div className={styles.statMeta}>{footer}</div>
      </div>
      <div className={styles.miniTrend}>
        <MiniTrendChart data={noDataType === 'error' ? [] : trendData} color={color} />
      </div>
    </div>
  );
};

export default function MysqlDashboardPage() {
  const { getInstanceQuery } = useViewApi();
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
  const [collectionStatusMetric, setCollectionStatusMetric] = useState<MetricSeries | null>(null);

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
  const primaryInstanceText =
    normalizeDisplayText(instanceName) || normalizeDisplayText(String(instanceId)) || normalizeDisplayText(idValues[0]) || '--';
  const objectDisplayText = normalizeDisplayText(monitorObjDisplayName) || normalizeDisplayText(monitorObjectName) || 'MySQL';
  const isDashboardMode = displayMode === 'dashboard';

  const loadMetrics = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }

    try {
      if (isDashboardMode) {
        const metricResultsPromise = Promise.all(
          DASHBOARD_METRICS.map((metric) =>
            getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues))
              .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, instanceName, idValues, instanceIdKeys)] as const)
              .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
        );

        const collectionStatusPromise = getInstanceQuery(buildSearchParams(MYSQL_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues))
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
              instanceName,
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
                unit: 'counts',
                query: MYSQL_COLLECTION_STATUS_QUERY,
                color: '#27c274',
                viewData: [],
                loadState: 'error' as const
              })
          );

        const [results, collectionStatus] = await Promise.all([
          metricResultsPromise,
          collectionStatusPromise
        ]);

        setSeries(Object.fromEntries(results));
        setCollectionStatusMetric(collectionStatus);
      } else {
        setSeries({});
        setCollectionStatusMetric(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMetrics();
  }, [instanceId, instanceName, JSON.stringify(idValues), timeValues, isDashboardMode]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [frequence, timeValues, instanceId, instanceName, JSON.stringify(idValues)]);

  const metricMap = useMemo(() => series, [series]);
  const dashboardMetrics = useMemo(
    () => DASHBOARD_METRICS.map((metric) => metricMap[metric.name] || { ...metric, viewData: [], loadState: 'success' as const }),
    [metricMap]
  );

  const getLatest = (name: string) => {
    const target = metricMap[name];
    return getLatestChartValue(target?.viewData || []);
  };

  const qpsValue = getLatest('mysql_queries_rate');
  const connValue = getLatest('mysql_connection_utilization');
  const slowValue = getLatest('mysql_slow_queries_rate');
  const hitValue = getLatest('mysql_buffer_pool_hit_ratio');
  const threadsConnectedValue = getLatest('mysql_threads_connected');
  const threadsRunningValue = getLatest('mysql_threads_running');
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
  const tmpDiskRatio = getLatest('mysql_tmp_disk_table_ratio');
  const tmpDiskRate = getLatest('mysql_created_tmp_disk_tables_rate');
  const tmpMemoryRate = getLatest('mysql_created_tmp_memory_tables_rate');
  const tmpTotalRate = getLatest('mysql_created_tmp_tables_rate');
  const lockWait = getLatest('mysql_innodb_row_lock_time_avg');
  const lockWaitRate = getLatest('mysql_innodb_row_lock_waits_rate');
  const openTables = getLatest('mysql_open_tables');
  const openFiles = getLatest('mysql_open_files');
  const openedTablesRate = getLatest('mysql_opened_tables_rate');
  const tableOpenCacheUtilization = getLatest('mysql_table_open_cache_utilization');
  const openFilesUtilization = getLatest('mysql_open_files_utilization');
  const tableCacheHitRatio = getLatest('mysql_table_open_cache_hits_rate');
  const tableCacheMissRate = getLatest('mysql_table_open_cache_misses_rate');
  const abortedClients = getLatest('mysql_aborted_clients');
  const maxConnectionErrors = getLatest('mysql_connection_errors_max_connections');
  const replicationDelay = getLatest('mysql_slave_seconds_behind_master');
  const replicationIoRunning = getLatest('mysql_slave_io_running');
  const replicationSqlRunning = getLatest('mysql_slave_sql_running');
  const readOnlyValue = getLatest('mysql_variables_read_only');
  const superReadOnlyValue = getLatest('mysql_variables_super_read_only');
  const logBinValue = getLatest('mysql_variables_log_bin');
  const logSlaveUpdatesValue = getLatest('mysql_variables_log_slave_updates');
  const statusInfo = getCollectionStatus(collectionStatusMetric);
  const roleText = inferMysqlRole({
    readOnly: readOnlyValue,
    superReadOnly: superReadOnlyValue,
    logBin: logBinValue,
    logSlaveUpdates: logSlaveUpdatesValue
  });

  const qpsDisplay = formatMetricValue(qpsValue, 'cps');
  const connDisplay = formatMetricValue(connValue, 'percent');
  const slowDisplay = formatMetricValue(slowValue * 60, 'permin');
  const hitDisplay = formatMetricValue(hitValue, 'percent');
  const replicationDelayDisplay = formatMetricValue(replicationDelay, 'counts');
  const pageTitle = displayMode === 'metrics' ? `${objectDisplayText} 全量指标` : 'MySQL 监控仪表盘';
  const hasDashboardContent = dashboardMetrics.length > 0;
  const showEmpty = isDashboardMode ? !hasDashboardContent : false;

  const qpsTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_queries_rate',
          label: 'QPS（每秒查询数）',
          displayName: 'QPS',
          data: metricMap.mysql_queries_rate?.viewData || []
        },
        {
          key: 'mysql_slow_queries_rate',
          label: '慢查询速率（次/分钟）',
          displayName: '慢查询速率',
          data: metricMap.mysql_slow_queries_rate?.viewData || []
        }
      ]),
    [metricMap.mysql_queries_rate?.viewData, metricMap.mysql_slow_queries_rate?.viewData]
  );

  const connectionTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_threads_connected',
          label: '当前连接数',
          displayName: '当前连接数',
          data: metricMap.mysql_threads_connected?.viewData || []
        },
        {
          key: 'mysql_threads_running',
          label: '执行线程数',
          displayName: '活跃线程数',
          data: metricMap.mysql_threads_running?.viewData || []
        }
      ]),
    [
      metricMap.mysql_threads_connected?.viewData,
      metricMap.mysql_threads_running?.viewData
    ]
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
          label: 'Redo 刷盘速率',
          displayName: 'Redo 刷盘速率',
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

  const networkTrendData = useMemo(
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

  const statementShare = [
    { name: 'SELECT', value: selectValue, color: '#2f6bff' },
    { name: 'INSERT', value: insertValue, color: '#ff8a1f' },
    { name: 'UPDATE', value: updateValue, color: '#faad14' },
    { name: 'DELETE', value: deleteValue, color: '#ff4d4f' }
  ];

  const totalStatements = statementShare.reduce((sum, item) => sum + item.value, 0);
  const threadShare = [
    {
      name: '运行中',
      value: Math.min(threadsRunningValue, threadsConnectedValue),
      color: '#2f6bff'
    },
    {
      name: '空闲中',
      value: Math.max(threadsConnectedValue - threadsRunningValue, 0),
      color: '#ff8a1f'
    }
  ];

  const onTimeChange = (val: number[], originValue: number | null) => {
    setTimeValues({
      timeRange: val,
      originValue
    });
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    setTimeDefaultValue((prev) => ({
      ...prev,
      rangePickerVaule: arr,
      selectValue: 0
    }));
    setTimeValues({
      timeRange: arr.map((item) => dayjs(item).valueOf()),
      originValue: 0
    });
  };

  const disableAutoRefresh = () => {
    setFrequence(0);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const goBack = () => {
    router.push('/monitor/view');
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
        <div className={styles.header}>
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>{pageTitle}</h1>
            <div className={`${styles.instanceCard} ${!isDashboardMode ? styles.instanceCardFull : ''}`}>
              <div className={styles.instanceIcon}>
                <DatabaseOutlined />
              </div>
              <div className={styles.instanceInfo}>
                <div className={styles.meta}>
                  <span className={styles.instanceName}>{primaryInstanceText}</span>
                  <Tooltip title={statusInfo.detail}>
                    <Tag color={statusInfo.tagColor}>{statusInfo.label}</Tag>
                  </Tooltip>
                  <span><ClockCircleOutlined /> 30 秒前</span>
                </div>
                <div className={styles.instanceSubline}>
                  <span className={styles.instanceMetaInline}>{primaryInstanceText}</span>
                  <span className={styles.instanceMetaDivider}>|</span>
                  <span className={styles.instanceMetaInline}>{objectDisplayText}</span>
                  <span className={styles.instanceMetaDivider}>|</span>
                  <span className={styles.instanceMetaInline}>{roleText}</span>
                  <span className={styles.instanceMetaDivider}>|</span>
                  <span className={styles.instanceMetaInline}>时区: Asia/Shanghai</span>
                  <span className={styles.instanceMetaDivider}>|</span>
                  <span className={styles.instanceMetaInline}>采集间隔: 10s</span>
                </div>
              </div>
            </div>
          </div>
          <div className={styles.controls}>
            <Segmented
              value={displayMode}
              onChange={(value) => setDisplayMode(value as 'dashboard' | 'metrics')}
              options={[
                { label: '专业仪表盘', value: 'dashboard' },
                { label: '全量指标', value: 'metrics' }
              ]}
            />
            <TimeSelector
              defaultValue={timeDefaultValue}
              onChange={onTimeChange}
              onFrequenceChange={disableAutoRefresh}
              onRefresh={() => loadMetrics()}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadMetrics()} />
            <Button icon={<ArrowLeftOutlined />} onClick={goBack}>返回</Button>
          </div>
        </div>

        <Spin spinning={loading}>
          {showEmpty ? (
            <div className={styles.empty}>
              <Empty description={t('common.noData')} />
            </div>
          ) : (
            <>
              {displayMode === 'dashboard' ? (
                <div className={styles.modeContent}>
                  <div className={styles.primaryGrid}>
                  <StatCard
                  title="采集状态"
                  value={statusInfo.label}
                  unit=""
                  icon={<ApiOutlined />}
                  iconStyle={{ background: `${statusInfo.accentColor}1f`, color: statusInfo.accentColor }}
                  color={statusInfo.accentColor}
                  footer={<><span>{statusInfo.summary}</span><span>30 秒前</span></>}
                  trendData={collectionStatusMetric?.viewData || []}
                  noDataType={getNoDataType('mysql_collection_status')}
                 />
                <StatCard
                  title="连接使用率"
                  value={connDisplay.value}
                  unit={connDisplay.unit}
                  icon={<NodeIndexOutlined />}
                  iconStyle={{ background: 'rgba(255, 145, 20, 0.12)', color: '#ff8a1f' }}
                  color="#ff7a00"
                  footer={<><span>{threadsConnectedValue.toFixed(0)} 当前连接</span><span>{maxConnectionsValue.toFixed(0)} 上限</span></>}
                  trendData={metricMap.mysql_connection_utilization?.viewData || []}
                  noDataType={getNoDataType('mysql_connection_utilization')}
                />
                <StatCard
                  title="QPS（每秒查询数）"
                  value={qpsDisplay.value}
                  unit={qpsDisplay.unit}
                  icon={<ThunderboltOutlined />}
                  iconStyle={{ background: 'rgba(47, 107, 255, 0.12)', color: '#2f6bff' }}
                  color="#2f6bff"
                  footer={<><span><RiseOutlined /> SELECT 查询 {selectValue.toFixed(1)}/s</span></>}
                  trendData={metricMap.mysql_queries_rate?.viewData || []}
                  noDataType={getNoDataType('mysql_queries_rate')}
                />
                <StatCard
                  title="慢查询速率"
                  value={slowDisplay.value}
                  unit={slowDisplay.unit}
                  icon={<ClockCircleOutlined />}
                  iconStyle={{ background: 'rgba(255, 77, 79, 0.12)', color: '#ff4d4f' }}
                  color="#ff3030"
                  footer={<><span><FallOutlined /> 行锁等待 {lockWaitRate.toFixed(2)}/s</span></>}
                  trendData={metricMap.mysql_slow_queries_rate?.viewData || []}
                  noDataType={getNoDataType('mysql_slow_queries_rate')}
                />
                <StatCard
                  title="Buffer Pool 命中率"
                  value={hitDisplay.value}
                  unit={hitDisplay.unit}
                  icon={<AppstoreOutlined />}
                  iconStyle={{ background: 'rgba(39, 194, 116, 0.12)', color: '#27c274' }}
                  color="#27c274"
                  footer={<><span>使用率 {bpUsedValue.toFixed(1)}%</span><span>脏页 {bpDirtyValue.toFixed(1)}%</span></>}
                  trendData={metricMap.mysql_buffer_pool_hit_ratio?.viewData || []}
                  noDataType={getNoDataType('mysql_buffer_pool_hit_ratio')}
                />
                  </div>

                  <div className={styles.panelGrid}>
                <div className={`${styles.panel} ${styles.chartPanel}`}>
                  <div className={styles.panelHeader}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}>QPS 与慢查询趋势</h3>
                      <div className={styles.chartLegend}>
                        {TREND_LEGENDS.qps.map((item) => (
                          <span className={styles.chartLegendItem} key={item.label}>
                            <span className={styles.chartLegendDot} style={{ background: item.color }} />
                            {item.label}
                          </span>
                        ))}
                      </div>
                    </div>
                    <span className={styles.panelHint}>总吞吐 | 慢 SQL</span>
                  </div>
                  <div className={styles.chartWrap}>
                    <LineChart
                      data={qpsTrendData}
                        metric={buildMetricItem(metricMap.mysql_queries_rate || dashboardMetrics[0])}
                      unit="cps"
                      xAxisTimeFormat="HH:mm"
                      leftAxisWidthOverride={44}
                      seriesStyles={TREND_LEGENDS.qps.map((item) => ({
                        color: item.color,
                        fillOpacity: item.primary ? 0.09 : 0.025,
                        strokeOpacity: item.primary ? 1 : 0.62,
                        strokeWidth: item.primary ? 2.8 : 2.1
                      }))}
                      onXRangeChange={onXRangeChange}
                      noDataType={getNoDataType('mysql_queries_rate', 'mysql_slow_queries_rate')}
                    />
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.chartPanel}`}>
                  <div className={styles.panelHeader}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}>连接与线程趋势</h3>
                      <div className={styles.chartLegend}>
                        {TREND_LEGENDS.connection.map((item) => (
                          <span className={styles.chartLegendItem} key={item.label}>
                            <span
                              className={`${styles.chartLegendDot} ${item.dashed ? styles.chartLegendDash : ''}`}
                              style={{ background: item.dashed ? 'transparent' : item.color, borderColor: item.color }}
                            />
                            {item.label}
                          </span>
                        ))}
                      </div>
                    </div>
                    <span className={styles.panelHint}>连接总量 | 执行线程</span>
                  </div>
                  <div className={styles.chartWrap}>
                    <LineChart
                      data={connectionTrendData}
                        metric={buildMetricItem(metricMap.mysql_threads_connected || dashboardMetrics[0])}
                      unit="counts"
                      xAxisTimeFormat="HH:mm"
                      leftAxisWidthOverride={44}
                      seriesStyles={TREND_LEGENDS.connection.map((item) => ({
                        color: item.color,
                        fillOpacity: item.primary ? 0.08 : 0.03,
                        strokeOpacity: item.primary ? 1 : 0.68,
                        strokeWidth: item.primary ? 2.8 : 2.2
                      }))}
                      onXRangeChange={onXRangeChange}
                      noDataType={getNoDataType('mysql_threads_connected', 'mysql_threads_running')}
                    />
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.chartPanel}`}>
                  <div className={styles.panelHeader}>
                    <h3 className={styles.panelTitle}>SQL 与线程构成</h3>
                    <span className={styles.panelHint}>查询结构与线程分布</span>
                  </div>
                  <div className={styles.compositeSplit}>
                    <div className={styles.compositeSection}>
                      <div className={styles.sectionMiniHeader}>查询类型分布</div>
                      <div className={styles.ringCard}>
                        <div className={styles.ringChartWrap}>
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={statementShare}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={82}
                                paddingAngle={2}
                                dataKey="value"
                              >
                                {statementShare.map((item) => (
                                  <Cell key={item.name} fill={item.color} />
                                ))}
                              </Pie>
                            </PieChart>
                          </ResponsiveContainer>
                          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                            <div className={styles.ringValue}>{qpsDisplay.value}</div>
                            <div className={styles.ringCaption}>每秒查询数</div>
                          </div>
                        </div>
                        <div className={styles.ringInfoPanel}>
                            <div className={styles.metricList}>
                              {statementShare.map((item) => (
                              <div className={styles.metricRow} key={item.name}>
                                <span className={styles.metricKey}>{item.name}</span>
                                <span className={styles.metricPercent}>
                                  {totalStatements > 0 ? ((item.value / totalStatements) * 100).toFixed(1) : '0.0'}%
                                </span>
                                <span className={styles.metricVal}>{item.value.toFixed(1)}/s</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className={styles.compositeSection}>
                      <div className={styles.sectionMiniHeader}>线程状态分布</div>
                      <div className={styles.ringCard}>
                        <div className={styles.ringChartWrap}>
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={threadShare}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={82}
                                paddingAngle={2}
                                dataKey="value"
                              >
                                {threadShare.map((item) => (
                                  <Cell key={item.name} fill={item.color} />
                                ))}
                              </Pie>
                            </PieChart>
                          </ResponsiveContainer>
                          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                            <div className={styles.ringValue}>{threadsConnectedValue.toFixed(0)}</div>
                            <div className={styles.ringCaption}>当前连接</div>
                          </div>
                        </div>
                        <div className={styles.ringInfoPanel}>
                            <div className={styles.metricList}>
                              {threadShare.map((item) => (
                              <div className={styles.metricRow} key={item.name}>
                                <span className={styles.metricKey}>{item.name}</span>
                                <span className={styles.metricPercent}>
                                  {threadsConnectedValue > 0 ? ((item.value / threadsConnectedValue) * 100).toFixed(1) : '0.0'}%
                                </span>
                                <span className={styles.metricVal}>{item.value.toFixed(0)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.chartPanel}`}>
                  <div className={styles.panelHeader}>
                    <h3 className={styles.panelTitle}>表与锁等待压力</h3>
                    <span className={styles.panelHint}>临时表、缓存命中、锁等待与连接异常</span>
                  </div>
                  <div className={styles.compositeSplit}>
                    <div className={styles.compositeSection}>
                      <div className={styles.sectionMiniHeader}>临时表与缓存压力（每分钟）</div>
                      <div className={styles.bars}>
                        {[
                          {
                            label: '磁盘临时表',
                            value: tmpDiskRate * 60,
                            display: `${(tmpDiskRate * 60).toFixed(tmpDiskRate * 60 >= 10 ? 0 : 1)} /min`,
                            color: '#ff4d4f',
                            max: Math.max(tmpTotalRate * 60, 1)
                          },
                          {
                            label: '内存临时表',
                            value: tmpMemoryRate * 60,
                            display: `${(tmpMemoryRate * 60).toFixed(tmpMemoryRate * 60 >= 10 ? 0 : 1)} /min`,
                            color: '#fa8c16',
                            max: Math.max(tmpTotalRate * 60, 1)
                          },
                          {
                            label: '表缓存未命中',
                            value: tableCacheMissRate * 60,
                            display: `${(tableCacheMissRate * 60).toFixed(tableCacheMissRate * 60 >= 10 ? 0 : 1)} /min`,
                            color: '#faad14',
                            max: Math.max((tableCacheMissRate + openedTablesRate) * 60, 1)
                          },
                          {
                            label: '打开表速率',
                            value: openedTablesRate * 60,
                            display: `${(openedTablesRate * 60).toFixed(openedTablesRate * 60 >= 10 ? 0 : 1)} /min`,
                            color: '#2f6bff',
                            max: Math.max((openedTablesRate + tableCacheMissRate) * 60, 1)
                          }
                        ].map((item) => (
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
                      <div className={styles.inlineStats}>
                        <div className={styles.inlineStat}><span><ApiOutlined /> 打开表</span><strong>{openTables.toFixed(0)}</strong></div>
                        <div className={styles.inlineStat}><span><HddOutlined /> 表缓存使用率</span><strong>{tableOpenCacheUtilization.toFixed(1)}%</strong></div>
                        <div className={styles.inlineStat}><span><FieldTimeOutlined /> 磁盘临时表占比</span><strong>{tmpDiskRatio.toFixed(1)}%</strong></div>
                      </div>
                      <div className={styles.inlineStats}>
                        <div className={styles.inlineStat}><span>表缓存命中率</span><strong>{tableCacheHitRatio.toFixed(1)}%</strong></div>
                        <div className={styles.inlineStat}><span>打开文件数</span><strong>{openFiles.toFixed(0)}</strong></div>
                        <div className={styles.inlineStat}><span>文件句柄使用率</span><strong>{openFilesUtilization.toFixed(1)}%</strong></div>
                      </div>
                    </div>
                    <div className={styles.compositeSection}>
                      <div className={styles.sectionMiniHeader}>锁与连接异常</div>
                      <div className={styles.bars}>
                        {[
                          {
                            label: '行锁等待',
                            value: lockWaitRate * 60,
                            display: `${(lockWaitRate * 60).toFixed(lockWaitRate * 60 >= 10 ? 0 : 1)} /min`,
                            color: '#ff4d4f',
                            max: Math.max(lockWaitRate * 60, 1)
                          },
                          {
                            label: '平均等待时间',
                            value: lockWait,
                            display: `${lockWait.toFixed(lockWait >= 10 ? 0 : 1)} ms`,
                            color: '#faad14',
                            max: Math.max(lockWait, 10)
                          },
                          {
                            label: '异常断开客户端',
                            value: abortedClients,
                            display: abortedClients.toFixed(abortedClients >= 10 ? 0 : 1),
                            color: '#52c41a',
                            max: Math.max(abortedClients, 1)
                          },
                          {
                            label: '达到连接上限',
                            value: maxConnectionErrors,
                            display: maxConnectionErrors.toFixed(maxConnectionErrors >= 10 ? 0 : 1),
                            color: '#2f6bff',
                            max: Math.max(maxConnectionErrors, 1)
                          }
                        ].map((item) => (
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
                      <div className={styles.inlineStats}>
                        <div className={styles.inlineStat}><span>当前等待等级</span><strong>{lockWait >= 50 ? '高' : lockWait >= 10 ? '中' : '低'}</strong></div>
                        <div className={styles.inlineStat}><span>锁等待频次</span><strong>{(lockWaitRate * 60).toFixed(1)}/min</strong></div>
                        <div className={styles.inlineStat}><span>连接异常画像</span><strong>{maxConnectionErrors > 0 ? '容量受限' : abortedClients > 0 ? '链路抖动' : '稳定'}</strong></div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.fullPanel}`}>
                  <div className={styles.panelHeader}>
                    <h3 className={styles.panelTitle}>存储与缓存效率</h3>
                    <span className={styles.panelHint}>InnoDB IO、缓存池与网络发送</span>
                  </div>
                  <div className={styles.storageComposite}>
                    <div className={styles.storageMain}>
                      <div>
                        <div className={styles.sectionMiniHeader}>InnoDB 读写趋势</div>
                        <div className={styles.chartLegend}>
                          {TREND_LEGENDS.innodb.map((item) => (
                            <span className={styles.chartLegendItem} key={item.label}>
                              <span className={styles.chartLegendDot} style={{ background: item.color }} />
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className={styles.chartWrap}>
                        <LineChart
                          data={innodbTrendData}
                           metric={buildMetricItem(metricMap.mysql_innodb_data_reads_rate || dashboardMetrics[0])}
                          unit="ops"
                          xAxisTimeFormat="HH:mm"
                          seriesStyles={TREND_LEGENDS.innodb.map((item) => ({
                            color: item.color,
                            fillOpacity: item.primary ? 0.08 : 0.03,
                            strokeOpacity: item.primary ? 1 : 0.68,
                            strokeWidth: item.primary ? 2.8 : 2.1
                          }))}
                          onXRangeChange={onXRangeChange}
                          noDataType={getNoDataType('mysql_innodb_data_reads_rate', 'mysql_innodb_data_writes_rate', 'mysql_innodb_os_log_fsyncs_rate')}
                        />
                      </div>
                      <div className={styles.inlineStats}>
                        <div className={styles.inlineStat}><span>读 IOPS</span><strong>{dataReadValue.toFixed(1)}/s</strong></div>
                        <div className={styles.inlineStat}><span>写 IOPS</span><strong>{dataWriteValue.toFixed(1)}/s</strong></div>
                        <div className={styles.inlineStat}><span>Redo 刷盘</span><strong>{fsyncValue.toFixed(1)}/s</strong></div>
                      </div>
                    </div>
                    <div className={styles.storageSide}>
                      <div className={styles.storageSubCard}>
                        <div className={styles.sectionMiniHeader}>Buffer Pool 使用情况</div>
                        <div className={styles.ringCard}>
                          <div className={styles.ringChartWrap}>
                            <ResponsiveContainer width="100%" height="100%">
                              <PieChart>
                                <Pie
                                  data={[
                                    { name: '已使用', value: Math.max(bpUsedValue, 0), color: '#2f6bff' },
                                    { name: '空闲', value: Math.max(100 - bpUsedValue, 0), color: '#d9e4ff' }
                                  ]}
                                  innerRadius={56}
                                  outerRadius={82}
                                  dataKey="value"
                                >
                                  <Cell fill="#2f6bff" />
                                  <Cell fill="#d9e4ff" />
                                </Pie>
                              </PieChart>
                            </ResponsiveContainer>
                            <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                              <div className={styles.ringValue}>{bpUsedValue.toFixed(0)}%</div>
                              <div className={styles.ringCaption}>使用率</div>
                            </div>
                          </div>
                          <div className={styles.ringInfoPanel}>
                            <div className={styles.metricList}>
                              <div className={styles.metricRow}><span className={styles.metricKey}>总页数</span><span className={styles.metricVal}>{getLatest('mysql_innodb_buffer_pool_pages_total').toLocaleString()}</span></div>
                              <div className={styles.metricRow}><span className={styles.metricKey}>空闲页数</span><span className={styles.metricVal}>{getLatest('mysql_innodb_buffer_pool_pages_free').toLocaleString()}</span></div>
                              <div className={styles.metricRow}><span className={styles.metricKey}>脏页数</span><span className={styles.metricVal}>{getLatest('mysql_innodb_buffer_pool_pages_dirty').toLocaleString()}</span></div>
                              <div className={styles.metricRow}><span className={styles.metricKey}>命中率</span><span className={styles.metricVal}>{hitValue.toFixed(1)}%</span></div>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className={styles.storageSubCard}>
                        <div className={styles.sectionMiniHeader}>网络收发趋势</div>
                        <div className={styles.chartLegend}>
                          {TREND_LEGENDS.network.map((item) => (
                            <span className={styles.chartLegendItem} key={item.label}>
                              <span className={styles.chartLegendDot} style={{ background: item.color }} />
                              {item.label}
                            </span>
                          ))}
                        </div>
                        <div className={styles.compactTrendWrap}>
                          <LineChart
                            data={networkTrendData}
                             metric={buildMetricItem(metricMap.mysql_bytes_sent_rate || metricMap.mysql_bytes_received_rate || dashboardMetrics[0])}
                            unit="byteps"
                            xAxisTimeFormat="HH:mm"
                            seriesStyles={TREND_LEGENDS.network.map((item) => ({
                              color: item.color,
                              fillOpacity: item.primary ? 0.08 : 0.025,
                              strokeOpacity: item.primary ? 1 : 0.66,
                              strokeWidth: item.primary ? 2.7 : 2.1
                            }))}
                            onXRangeChange={onXRangeChange}
                            noDataType={getNoDataType('mysql_bytes_received_rate', 'mysql_bytes_sent_rate')}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className={`${styles.panel} ${styles.chartPanel}`}>
                  <div className={styles.panelHeader}>
                    <h3 className={styles.panelTitle}>复制状态（从库）</h3>
                    <span className={styles.panelHint}>复制延迟 | IO 线程 | SQL 线程</span>
                  </div>
                  <div className={styles.compositeSection}>
                    <div className={styles.replicationSummary}>
                      <div className={styles.replicationDelayBlock}>
                        <div className={styles.replicationDelayLabel}>复制延迟</div>
                        <div className={styles.replicationDelayValue}>{replicationDelayDisplay.value}<span>{replicationDelayDisplay.unit || 's'}</span></div>
                      </div>
                      <div className={styles.replicationStatusList}>
                        <div className={styles.replicationStatusItem}><span>IO 线程</span><Tag color={replicationIoRunning > 0 ? 'success' : 'error'}>{replicationIoRunning > 0 ? '运行中' : '已停止'}</Tag></div>
                        <div className={styles.replicationStatusItem}><span>SQL 线程</span><Tag color={replicationSqlRunning > 0 ? 'success' : 'error'}>{replicationSqlRunning > 0 ? '运行中' : '已停止'}</Tag></div>
                      </div>
                    </div>
                    <div className={styles.replicationChartWrap}>
                      <LineChart
                        data={replicationTrendData}
                        metric={buildMetricItem(metricMap.mysql_slave_seconds_behind_master || dashboardMetrics[0])}
                        unit="counts"
                        xAxisTimeFormat="HH:mm"
                        seriesStyles={TREND_LEGENDS.replication.map((item) => ({
                          color: item.color,
                          fillOpacity: 0.08,
                          strokeOpacity: 1,
                          strokeWidth: 2.8
                        }))}
                        onXRangeChange={onXRangeChange}
                        noDataType={getNoDataType('mysql_slave_seconds_behind_master')}
                      />
                    </div>
                  </div>
                </div>

                  </div>
                </div>
              ) : (
                <div className={`${styles.modeContent} ${styles.metricsMode}`}>
                  <div className={`${styles.panel} ${styles.fullPanel}`}>
                    <div className={styles.panelHeader}>
                      <div className={styles.panelHeading}>
                        <h3 className={styles.panelTitle}>监控指标全景</h3>
                        <div className={styles.panelSubTitle}>复用详情页的通用监控视图能力，减少专业仪表盘重复维护</div>
                      </div>
                    </div>
                    <MetricViews
                      monitorObjectId={monitorObjectId}
                      monitorObjectName={monitorObjectName}
                      instanceId={String(instanceId)}
                      instanceName={instanceName}
                      idValues={idValues}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </Spin>
      </div>
    </div>
  );
}
