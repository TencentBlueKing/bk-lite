'use client';

import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Button, Empty, Select, Spin, Tag, Tooltip } from 'antd';
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  RiseOutlined,
  FallOutlined,
  NodeIndexOutlined,
  CodeOutlined,
  DesktopOutlined,
  HddOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import { Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import TimeSelector from '@/components/time-selector';
import LineChart from '@/app/monitor/components/charts/lineChart';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import { useTranslation } from '@/utils/i18n';
import { ListItem } from '@/types';
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
import { MetricSeries, MetricUnit, MysqlMetricConfig } from './types';
import styles from './index.module.scss';
import useMonitorApi from '@/app/monitor/api';

interface MysqlInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens: string[];
}

const MAX_POINTS = 100;
const DEFAULT_STEP = 360;
const MYSQL_REFRESH_FREQUENCY_LIST: ListItem[] = [
  { label: '关闭', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '2m', value: 120000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 }
];
const RAW_VALUE_METRICS = new Set([
  'mysql_uptime',
  'mysql_innodb_buffer_pool_pages_total',
  'mysql_innodb_buffer_pool_pages_free',
  'mysql_innodb_buffer_pool_pages_dirty'
]);
const CONNECTION_ERROR_LABELS: Record<string, string> = {
  mysql_aborted_connects: '连接尝试失败数',
  mysql_aborted_clients: '客户端异常断开数',
  mysql_connection_errors_internal: '内部连接错误数',
  mysql_connection_errors_max_connections: '连接数上限错误数',
  mysql_connection_errors_peer_address: '对端地址连接错误数',
  mysql_connection_errors_select: '轮询连接错误数',
  mysql_connection_errors_tcpwrap: '访问控制连接错误数'
};
const COLLECTION_STATUS_SEGMENT_COUNT = 18;
const COLLECTION_STATUS_LEGEND = [
  { key: 'success' as const, label: '正常', color: '#22c55e' },
  { key: 'empty' as const, label: '无数据', color: '#cbd5e1' },
  { key: 'error' as const, label: '异常', color: '#ff4d4f' }
];

const formatMetricValue = (value: number, unit: MetricUnit) => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  if (unit === 's') {
    if (value < 60) {
      return { value: value.toFixed(0), unit: 's' };
    }

    if (value < 3600) {
      return { value: (value / 60).toFixed(value >= 600 ? 0 : 1), unit: 'min' };
    }

    if (value < 86400) {
      return { value: (value / 3600).toFixed(value >= 36000 ? 0 : 1), unit: 'h' };
    }

    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    return { value: `${days}${hours > 0 ? `d ${hours}h` : 'd'}`, unit: '' };
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
    source_unit,
    auto_convert_unit: Array.from(RAW_VALUE_METRICS).some((metricName) => query.includes(metricName)) ? false : true
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

const getChartPointSeriesTotal = (point?: ChartData) => {
  if (!point) {
    return 0;
  }

  return Object.entries(point).reduce((sum, [key, value]) => {
    if (!/^value\d+$/.test(key) || typeof value !== 'number' || !Number.isFinite(value)) {
      return sum;
    }

    return sum + value;
  }, 0);
};

const buildSeriesTotalByTime = (data: ChartData[] = []) => {
  const totals = new Map<number, number>();

  data.forEach((point) => {
    const time = Number(point.time);
    if (!Number.isFinite(time)) {
      return;
    }

    totals.set(time, getChartPointSeriesTotal(point));
  });

  return totals;
};

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

const buildPreviousPeriodTimeValues = (timeValues: TimeValuesProps): TimeValuesProps | null => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);

  if (!startTime || !endTime) {
    return null;
  }

  const duration = endTime - startTime;

  return {
    timeRange: [startTime - duration, endTime - duration],
    originValue: 0
  };
};

const getPeriodCompare = (currentValue: number, previousValue: number) => {
  if (!Number.isFinite(currentValue) || !Number.isFinite(previousValue)) {
    return null;
  }

  if (previousValue === 0) {
    if (currentValue === 0) {
      return { direction: 'flat' as const, value: '0.0%' };
    }

    return null;
  }

  const delta = ((currentValue - previousValue) / Math.abs(previousValue)) * 100;

  if (Math.abs(delta) < 0.05) {
    return { direction: 'flat' as const, value: '0.0%' };
  }

  return {
    direction: delta > 0 ? ('up' as const) : ('down' as const),
    value: `${Math.abs(delta).toFixed(1)}%`
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

const countRestartsInRange = (data: ChartData[] = []) => {
  const points = [...data]
    .map((point) => ({
      time: Number(point.time),
      value: getChartPointSeriesTotal(point)
    }))
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value) && point.value >= 0)
    .sort((a, b) => a.time - b.time);

  if (points.length < 2) {
    return 0;
  }

  let restartCount = 0;

  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const drop = previous.value - current.value;
    const gapSeconds = Math.max((current.time - previous.time) / 1000, 0);
    const tolerance = Math.max(30, gapSeconds * 0.2);

    if (drop > tolerance && current.value < previous.value * 0.98) {
      restartCount += 1;
    }
  }

  return restartCount;
};

const getCompareTone = (direction: 'up' | 'down' | 'flat') => {
  if (direction === 'flat') {
    return 'flat';
  }

  return direction === 'up' ? 'positive' : 'negative';
};

const normalizeDisplayText = (value?: string | null) => {
  if (!value) {
    return '';
  }

  const trimmed = value.trim();
  if (!trimmed || trimmed === '--') {
    return '';
  }

  const withoutQuotes = trimmed.replace(/^["'`\[(,\s]+|["'`,;\])\s]+$/g, '').trim();
  if (!withoutQuotes || withoutQuotes === '--') {
    return '';
  }

  if (/^[A-Za-z0-9+/=_-]{12,}$/.test(withoutQuotes) && !/[.:/]/.test(withoutQuotes)) {
    return '';
  }

  return withoutQuotes;
};

const isOpaqueIdentifier = (value?: string | null) => {
  const normalized = normalizeDisplayText(value);
  if (!normalized) {
    return true;
  }

  return /^[A-Za-z0-9+/=_-]{12,}$/.test(normalized) && !/[.:/]/.test(normalized);
};

const buildInstanceDisplayName = (item: any) => {
  const primaryName = normalizeDisplayText(item.instance_name) || normalizeDisplayText(item.name);
  const hostPort = normalizeDisplayText(item.host && item.port ? `${item.host}:${item.port}` : '');
  const endpoint = normalizeDisplayText(item.endpoint) || normalizeDisplayText(item.url);
  const fallbackHost = normalizeDisplayText(item.host) || normalizeDisplayText(item.ip);

  if (primaryName && hostPort && !primaryName.includes(hostPort)) {
    return `${primaryName} (${hostPort})`;
  }

  if (primaryName) {
    return primaryName;
  }

  return hostPort || endpoint || fallbackHost || normalizeDisplayText(item.instance_id) || '--';
};

const buildInstanceSearchTokens = (item: any, displayName: string) => {
  return Array.from(
    new Set(
      [
        displayName,
        normalizeDisplayText(item.instance_name),
        normalizeDisplayText(item.name),
        normalizeDisplayText(item.host),
        normalizeDisplayText(item.ip),
        normalizeDisplayText(item.port),
        normalizeDisplayText(item.endpoint),
        normalizeDisplayText(item.url),
        normalizeDisplayText(item.instance_id)
      ].filter(Boolean)
    )
  );
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

const inferMysqlIdentity = (roleSignals: {
  instanceName: string;
  hasReplicationMetrics: boolean;
  hasReplicaRuntime: boolean;
  replicationDelay: number;
  replicationIoRunning: number;
  replicationSqlRunning: number;
  readOnly: number;
  superReadOnly: number;
  logBin: number;
  logSlaveUpdates: number;
}) => {
  const {
    instanceName,
    hasReplicationMetrics,
    hasReplicaRuntime,
    replicationDelay,
    replicationIoRunning,
    replicationSqlRunning,
    readOnly,
    superReadOnly,
    logBin,
    logSlaveUpdates
  } =
    roleSignals;
  const normalizedName = instanceName.toLowerCase();
  const nameSaysStandalone = /单点|单节点|独立|standalone|single/.test(normalizedName);
  const nameSaysReplica = /从库|从节点|slave|replica|secondary/.test(normalizedName);
  const nameSaysPrimary = /主库|主节点|master|primary/.test(normalizedName);

  const hasReplicaSignals = replicationIoRunning > 0 || replicationSqlRunning > 0 || replicationDelay > 0;
  const isReadonlyReplica = readOnly > 0 || superReadOnly > 0;
  const hasReplicaIdentity = nameSaysReplica || hasReplicaSignals || isReadonlyReplica || hasReplicaRuntime;
  const hasPrimaryIdentity = nameSaysPrimary || (logBin > 0 && (hasReplicationMetrics || logSlaveUpdates > 0));
  const deployment = nameSaysStandalone
    ? '单节点'
    : hasReplicaIdentity || hasPrimaryIdentity || logSlaveUpdates > 0
      ? '主从复制'
      : '单节点';
  const role = hasReplicaIdentity ? '从库' : deployment === '主从复制' && hasPrimaryIdentity ? '主库' : '独立实例';
  const replication = deployment === '单节点' ? '不适用' : role === '从库' ? '从库复制' : '源端复制';

  return { deployment, role, replication };
};

const getCollectionStatusTones = (metric?: MetricSeries | null) => {
  if (!Array.isArray(metric?.viewData)) {
    return [] as Array<'success' | 'empty'>;
  }

  return [...metric.viewData]
    .sort((a, b) => Number(a.time) - Number(b.time))
    .slice(-COLLECTION_STATUS_SEGMENT_COUNT)
    .map((point) => (Number(point.value1 ?? 0) > 0 ? ('success' as const) : ('empty' as const)));
};

const buildCollectionStatusTimeline = (metric?: MetricSeries | null) => {
  if (metric?.loadState === 'error') {
    return Array.from({ length: COLLECTION_STATUS_SEGMENT_COUNT }, () => 'error' as const);
  }

  const tones = getCollectionStatusTones(metric);

  if (tones.length >= COLLECTION_STATUS_SEGMENT_COUNT) {
    return tones;
  }

  return [
    ...Array.from({ length: COLLECTION_STATUS_SEGMENT_COUNT - tones.length }, () => 'empty' as const),
    ...tones
  ];
};

const formatCollectionStatusWindow = (timeValues: TimeValuesProps) => {
  const [startTime, endTime] = getRecentTimeRange(timeValues);

  if (!startTime || !endTime) {
    return '最近 15 分钟';
  }

  const totalMinutes = Math.max(Math.round((endTime - startTime) / 60000), 1);

  if (totalMinutes < 60) {
    return `最近 ${totalMinutes} 分钟`;
  }

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  return minutes > 0 ? `最近 ${hours} 小时 ${minutes} 分钟` : `最近 ${hours} 小时`;
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
          label: series.displayName || '',
          value: series.displayName || series.label
        }
      ];

      merged.set(time, current);
    });
  });

  return Array.from(merged.values()).sort((a, b) => Number(a.time) - Number(b.time));
};

const getCollectionStatus = (metric?: MetricSeries | null) => {
  const hasError = metric?.loadState === 'error';

  if (hasError) {
    return {
      label: '异常',
      tagColor: 'error' as const,
      accentColor: '#ff4d4f',
      summary: '查询失败',
      detail: '当前采集状态指标查询失败，请检查探针与数据库连通性或采集配置。'
    };
  }

  const latestTone = getCollectionStatusTones(metric).at(-1);

  if (latestTone === 'success') {
    return {
      label: '正常',
      tagColor: 'success' as const,
      accentColor: '#27c274',
      summary: '采集中',
      detail: '当前采集状态指标可正常返回，说明 MySQL 监控探针采集链路正常。'
    };
  }

  return {
    label: '无数据',
    tagColor: 'warning' as const,
    accentColor: '#fa8c16',
    summary: '暂无采集数据',
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
  compare,
  trendData = [],
  hideTrend = false,
  noDataType = 'empty',
  className,
  bodyClassName,
  extra
}: {
  title: string;
  value: React.ReactNode;
  unit: string;
  icon: React.ReactNode;
  iconStyle: React.CSSProperties;
  color: string;
  footer: React.ReactNode;
  compare?: {
    direction: 'up' | 'down' | 'flat';
    value: string;
  } | null;
  trendData?: ChartData[];
  hideTrend?: boolean;
  noDataType?: 'empty' | 'error';
  className?: string;
  bodyClassName?: string;
  extra?: React.ReactNode;
}) => {
  const compareTone = compare ? getCompareTone(compare.direction) : 'flat';

  return (
    <div className={`${styles.statCard} ${className || ''}`}>
      <div className={styles.statHeader}>
        <div className={styles.statLabel}>{title}</div>
        <div className={styles.statIcon} style={iconStyle}>
          {icon}
        </div>
      </div>
      <div className={`${styles.statBody} ${bodyClassName || ''}`}>
        <div className={styles.statValue} style={{ color }}>
          {value}
          {unit ? <span className={styles.statUnit}>{unit}</span> : null}
        </div>
        {compare ? (
          <div className={`${styles.statCompare} ${styles[`statCompare${compareTone === 'flat' ? 'Flat' : compareTone === 'positive' ? 'Positive' : 'Negative'}`]}`}>
            <span className={styles.statCompareLabel}>较上一周期</span>
            <span className={styles.statCompareValue}>
              {compare.direction === 'up' ? <RiseOutlined /> : compare.direction === 'down' ? <FallOutlined /> : null}
              {compare.value}
            </span>
          </div>
        ) : null}
        <div className={styles.statMeta}>{footer}</div>
      </div>
      {extra ? <div className={styles.statExtra}>{extra}</div> : null}
      {!hideTrend ? (
        <div className={styles.miniTrend}>
          <MiniTrendChart data={noDataType === 'error' ? [] : trendData} color={color} />
        </div>
      ) : null}
    </div>
  );
};

const CollectionStatusCard = ({
  status,
  timeline,
  windowLabel
}: {
  status: ReturnType<typeof getCollectionStatus>;
  timeline: Array<'success' | 'empty' | 'error'>;
  windowLabel: string;
}) => {
  return (
    <div className={`${styles.statCard} ${styles.collectionStatusCard}`}>
      <div className={styles.collectionStatusHeader}>
        <div className={styles.statLabel}>采集状态</div>
      </div>
      <div className={styles.collectionStatusBody}>
        <div className={`${styles.collectionStatusValue} ${styles[`collectionStatusValue${status.label === '正常' ? 'Success' : status.label === '异常' ? 'Error' : 'Empty'}`]}`}>
          {status.label}
        </div>
        <div className={styles.collectionStatusTimelineBlock}>
          <div className={styles.collectionStatusTimelineTitle}>状态时间线</div>
          <div className={styles.collectionStatusTimeline}>
            {timeline.map((tone, index) => (
              <span key={`${tone}-${index}`} className={`${styles.collectionStatusSegment} ${styles[`collectionStatusSegment${tone === 'success' ? 'Success' : tone === 'error' ? 'Error' : 'Empty'}`]}`} />
            ))}
          </div>
          <div className={styles.collectionStatusLegend}>
            {COLLECTION_STATUS_LEGEND.map((item) => (
              <span key={item.key} className={styles.collectionStatusLegendItem}>
                <span className={styles.collectionStatusLegendDot} style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default function MysqlDashboardPage() {
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
            searchTokens: buildInstanceSearchTokens(item, label)
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
  const primaryInstanceText = resolvedInstanceName;

  const loadMetrics = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }

    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = DASHBOARD_METRICS.filter((metric) =>
          [
            'mysql_connection_utilization',
            'mysql_queries_rate',
            'mysql_slow_queries_rate',
            'mysql_buffer_pool_hit_ratio'
          ].includes(metric.name)
        );
        const metricResultsPromise = Promise.all(
          DASHBOARD_METRICS.map((metric) =>
            getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues))
              .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
              .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
        );

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(buildSearchParams(MYSQL_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues))
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
          ? Promise.all(
            compareMetrics.map((metric) =>
              getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, previousTimeValues))
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
  }, [instanceId, resolvedInstanceName, idValuesKey, timeValues, isDashboardMode]);

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (frequence > 0) {
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
  }, [frequence, timeValues, instanceId, resolvedInstanceName, idValuesKey, isDashboardMode]);

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
  const getMetricValue = (name: string, value: number) => (hasMetricData(name) ? value : 0);

  const qpsValue = getLatest('mysql_queries_rate');
  const connValue = getLatest('mysql_connection_utilization');
  const slowValue = getLatest('mysql_slow_queries_rate');
  const hitValue = getLatest('mysql_buffer_pool_hit_ratio');
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
  const tmpMemoryRate = getLatest('mysql_created_tmp_memory_tables_rate');
  const tmpTotalRate = getLatest('mysql_created_tmp_tables_rate');
  const lockWait = getLatest('mysql_innodb_row_lock_time_avg');
  const lockWaitRate = getLatest('mysql_innodb_row_lock_waits_rate');
  const openedTablesRate = getLatest('mysql_opened_tables_rate');
  const tableCacheMissRate = getLatest('mysql_table_open_cache_misses_rate');
  const abortedConnects = getLatest('mysql_aborted_connects');
  const abortedConnectsRate = getLatest('mysql_aborted_connects_rate');
  const abortedClients = getLatest('mysql_aborted_clients');
  const abortedClientsRate = getLatest('mysql_aborted_clients_rate');
  const internalConnectionErrors = getLatest('mysql_connection_errors_internal');
  const maxConnectionErrors = getLatest('mysql_connection_errors_max_connections');
  const maxConnectionErrorsRate = getLatest('mysql_connection_errors_max_connections_rate');
  const peerAddressConnectionErrors = getLatest('mysql_connection_errors_peer_address');
  const selectConnectionErrors = getLatest('mysql_connection_errors_select');
  const tcpwrapConnectionErrors = getLatest('mysql_connection_errors_tcpwrap');
  const replicationDelay = getLatest('mysql_slave_seconds_behind_master');
  const replicationIoRunning = getLatest('mysql_slave_io_running');
  const replicationSqlRunning = getLatest('mysql_slave_sql_running');
  const readOnlyValue = getLatest('mysql_variables_read_only');
  const superReadOnlyValue = getLatest('mysql_variables_super_read_only');
  const logBinValue = getLatest('mysql_variables_log_bin');
  const logSlaveUpdatesValue = getLatest('mysql_variables_log_slave_updates');
  const statusInfo = getCollectionStatus(collectionStatusMetric);
  const metricEmptyText = statusInfo.label === '异常' ? '查询失败' : '暂无采集数据';
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric);
  const collectionStatusWindowLabel = formatCollectionStatusWindow(timeValues);
  const qpsDisplay = formatMetricValue(qpsValue, 'cps');
  const connDisplay = formatMetricValue(connValue, 'percent');
  const slowDisplay = formatMetricValue(slowValue * 60, 'permin');
  const uptimeInsight = getUptimeInsight(uptimeValue);
  const replicationDelayDisplay = formatMetricValue(replicationDelay, 's');
  const connCompare = getPeriodCompare(connValue, getPreviousLatest('mysql_connection_utilization'));
  const hitCompare = getPeriodCompare(hitValue, getPreviousLatest('mysql_buffer_pool_hit_ratio'));
  const qpsCompare = getPeriodCompare(qpsValue, getPreviousLatest('mysql_queries_rate'));
  const slowCompare = getPeriodCompare(slowValue * 60, getPreviousLatest('mysql_slow_queries_rate') * 60);
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
        }
      ]),
    [metricMap.mysql_queries_rate?.viewData]
  );

  const slowQueryTrendData = useMemo(
    () =>
      mergeChartSeries([
        {
          key: 'mysql_slow_queries_rate',
          label: '慢查询速率（次/分钟）',
          displayName: '慢查询速率',
          data: (metricMap.mysql_slow_queries_rate?.viewData || []).map((point) => ({
            ...point,
            value1: Number(point.value1 ?? 0) * 60
          }))
        }
      ]),
    [metricMap.mysql_slow_queries_rate?.viewData]
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

  const statementKnownValue = Math.max(selectValue, 0) + Math.max(insertValue, 0) + Math.max(updateValue, 0) + Math.max(deleteValue, 0);
  const statementOtherValue = Math.max(qpsValue - statementKnownValue, 0);
  const statementShare = [
    { name: 'SELECT', value: selectValue, color: '#4c8dff' },
    { name: 'INSERT', value: insertValue, color: '#ff8f3d' },
    { name: 'UPDATE', value: updateValue, color: '#ffbf47' },
    { name: 'DELETE', value: deleteValue, color: '#ff627e' },
    { name: '其他', value: statementOtherValue, color: '#7f8da3' }
  ];
  const statementShareChartData = statementShare.filter((item) => item.value > 0);

  const totalStatements = statementShare.reduce((sum, item) => sum + item.value, 0);
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
  const bufferPoolHitRatio = Math.min(Math.max(hitValue, 0), 100);
  const bufferPoolDirtyRatio = Math.min(Math.max(bpDirtyValue, 0), bufferPoolUsedValue);
  const bufferPoolCleanUsedRatio = Math.max(bufferPoolUsedValue - bufferPoolDirtyRatio, 0);
  const bufferPoolShareChartData = [
    { name: '已用页', value: bufferPoolCleanUsedRatio, color: '#4c8dff' },
    { name: '脏页', value: bufferPoolDirtyRatio, color: '#ff9f43' },
    { name: '空闲页', value: Math.max(100 - bufferPoolUsedValue, 0), color: '#cbd5e1' }
  ].filter((item) => item.value > 0);
  const bufferPoolLegendItems = [
    { name: '已用页', value: bufferPoolCleanUsedRatio, color: '#4c8dff' },
    { name: '脏页', value: bufferPoolDirtyRatio, color: '#ff9f43' },
    { name: '空闲页', value: Math.max(100 - bufferPoolUsedValue, 0), color: '#cbd5e1' }
  ];
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

  const connectionErrorStats = [
    { label: CONNECTION_ERROR_LABELS.mysql_aborted_connects, value: abortedConnects, color: '#a855f7' },
    { label: CONNECTION_ERROR_LABELS.mysql_aborted_clients, value: abortedClients, color: '#ff4d4f' },
    { label: CONNECTION_ERROR_LABELS.mysql_connection_errors_internal, value: internalConnectionErrors, color: '#ff7a45' },
    { label: CONNECTION_ERROR_LABELS.mysql_connection_errors_max_connections, value: maxConnectionErrors, color: '#2f6bff' },
    { label: CONNECTION_ERROR_LABELS.mysql_connection_errors_peer_address, value: peerAddressConnectionErrors, color: '#13c2c2' },
    { label: CONNECTION_ERROR_LABELS.mysql_connection_errors_select, value: selectConnectionErrors, color: '#faad14' },
    { label: CONNECTION_ERROR_LABELS.mysql_connection_errors_tcpwrap, value: tcpwrapConnectionErrors, color: '#722ed1' }
  ].sort((a, b) => b.value - a.value);
  const connectionErrorRateStats = [
    {
      label: CONNECTION_ERROR_LABELS.mysql_aborted_connects,
      value: getMetricValue('mysql_aborted_connects_rate', abortedConnectsRate * 60),
      display: renderMetricValue('mysql_aborted_connects_rate', `${(abortedConnectsRate * 60).toFixed(abortedConnectsRate * 60 >= 10 ? 0 : 1)} /min`),
      cumulative: abortedConnects,
      color: '#a855f7'
    },
    {
      label: CONNECTION_ERROR_LABELS.mysql_aborted_clients,
      value: getMetricValue('mysql_aborted_clients_rate', abortedClientsRate * 60),
      display: renderMetricValue('mysql_aborted_clients_rate', `${(abortedClientsRate * 60).toFixed(abortedClientsRate * 60 >= 10 ? 0 : 1)} /min`),
      cumulative: abortedClients,
      color: '#52c41a'
    },
    {
      label: CONNECTION_ERROR_LABELS.mysql_connection_errors_max_connections,
      value: getMetricValue('mysql_connection_errors_max_connections_rate', maxConnectionErrorsRate * 60),
      display: renderMetricValue('mysql_connection_errors_max_connections_rate', `${(maxConnectionErrorsRate * 60).toFixed(maxConnectionErrorsRate * 60 >= 10 ? 0 : 1)} /min`),
      cumulative: maxConnectionErrors,
      color: '#2f6bff'
    }
  ];
  const totalConnectionErrors = connectionErrorStats.reduce((sum, item) => sum + item.value, 0);
  const topConnectionError = connectionErrorStats.find((item) => item.value > 0) || connectionErrorStats[0];
  const totalConnectionErrorRate = connectionErrorRateStats.reduce((sum, item) => sum + item.value, 0);
  const topConnectionErrorRate = connectionErrorRateStats.find((item) => item.value > 0) || connectionErrorRateStats[0];
  const totalConnectionErrorRateDisplay = `${totalConnectionErrorRate >= 100 ? totalConnectionErrorRate.toFixed(0) : totalConnectionErrorRate.toFixed(1)} /min`;

  const uptimeDisplay = hasMetricData('mysql_uptime') ? uptimeInsight.uptimeText : '--';
  const startupTimeDisplay = hasMetricData('mysql_uptime') ? uptimeInsight.startupTimeText : metricEmptyText;
  const uptimeRestarts = countRestartsInRange(metricMap.mysql_uptime?.viewData || []);
  const uptimeState = !hasMetricData('mysql_uptime')
    ? { label: '状态未知', detail: metricEmptyText, tone: 'empty' }
    : uptimeRestarts > 0
      ? { label: '期间有重启', detail: '', tone: 'warning' }
      : { label: '运行正常', detail: '', tone: 'success' };
  const uptimeStateGuide = [
    { label: '状态未知', detail: '当前观察范围内未获取到 mysql_uptime 指标，无法判断是否发生过重启。' },
    { label: '运行正常', detail: `当前所选时段（${collectionStatusWindowLabel}）内 mysql_uptime 未出现明显回退。该状态仅表示未观察到重启，不代表实例整体健康度。` },
    { label: '期间有重启', detail: `当前所选时段（${collectionStatusWindowLabel}）内 mysql_uptime 出现回退，说明实例在该时间段内发生过重启。以上状态仅描述重启观察结果，不代表实例整体健康度。` }
  ];
  const connCardDisplay = getDisplayValue('mysql_connection_utilization', connDisplay);
  const qpsCardDisplay = getDisplayValue('mysql_queries_rate', qpsDisplay);
  const slowCardDisplay = getDisplayValue('mysql_slow_queries_rate', slowDisplay);
  const hitCardDisplay = getDisplayValue('mysql_buffer_pool_hit_ratio', {
    value: bufferPoolHitRatio.toFixed(1),
    unit: '%'
  });
  const hasConnectionData = hasMetricData('mysql_connection_utilization');
  const hasQpsData = hasMetricData('mysql_queries_rate');
  const hasSlowData = hasMetricData('mysql_slow_queries_rate');
  const hasHitData = hasMetricData('mysql_buffer_pool_hit_ratio');
  const hasReplicationData =
    hasMetricData('mysql_slave_seconds_behind_master') ||
    hasMetricData('mysql_slave_io_running') ||
    hasMetricData('mysql_slave_sql_running');
  const mysqlIdentity = inferMysqlIdentity({
    instanceName: resolvedInstanceName,
    hasReplicationMetrics: hasReplicationData,
    hasReplicaRuntime: hasReplicationData && (replicationIoRunning > 0 || replicationSqlRunning > 0),
    replicationDelay,
    replicationIoRunning,
    replicationSqlRunning,
    readOnly: readOnlyValue,
    superReadOnly: superReadOnlyValue,
    logBin: logBinValue,
    logSlaveUpdates: logSlaveUpdatesValue
  });
  const instanceMetaItems = [
    instanceIdText ? <span key="instance-id" className={styles.instanceMetaInline}>{instanceIdText}</span> : null,
    <span key="object-name" className={styles.instanceMetaInline}>{objectDisplayText}</span>,
    <span key="identity" className={styles.instanceIdentityGroup}>
      <span className={styles.identityPill}>部署: {mysqlIdentity.deployment}</span>
      <span className={styles.identityPill}>身份: {mysqlIdentity.role}</span>
      <span className={styles.identityPill}>复制: {mysqlIdentity.replication}</span>
    </span>,
    <span key="timezone" className={styles.instanceMetaInline}>时区: Asia/Shanghai</span>
  ].filter(Boolean) as React.ReactNode[];
  const replicationApplicable = mysqlIdentity.role === '从库' || hasReplicationData;
  const renderFlowValue = (name: string, value: string, unit = '') => (hasMetricData(name) ? `${value}${unit}` : '--');
  const requestFlowNodes: Array<{
    title: string;
    subTitle: string;
    icon: React.ReactNode;
    className?: string;
    metrics: Array<{ label: string; value: string }>;
  }> = [
    {
      title: '客户端 / 连接',
      subTitle: '请求入口',
      icon: <DesktopOutlined />,
      metrics: [
        { label: 'QPS', value: `${qpsCardDisplay.value}${qpsCardDisplay.unit}` },
        {
          label: '当前连接',
          value: hasMetricData('mysql_threads_connected') ? threadsConnectedValue.toFixed(0) : '--'
        },
        { label: '连接使用率', value: `${connCardDisplay.value}${connCardDisplay.unit}` }
      ]
    },
    {
      title: 'MySQL 实例',
      subTitle: '实例信息',
      icon: <DatabaseOutlined />,
      metrics: [
        { label: '部署', value: mysqlIdentity.deployment },
        { label: '身份', value: mysqlIdentity.role },
        { label: '运行时长', value: uptimeDisplay },
      ]
    },
    {
      title: 'SQL 执行',
      subTitle: '查询 / 锁等待',
      icon: <CodeOutlined />,
      metrics: [
        { label: 'SELECT', value: renderFlowValue('mysql_com_select_rate', selectValue.toFixed(1), '/s') },
        { label: '慢查询', value: `${slowCardDisplay.value}${slowCardDisplay.unit}` },
        {
          label: '锁等待',
          value: renderFlowValue('mysql_innodb_row_lock_waits_rate', (lockWaitRate * 60).toFixed(lockWaitRate * 60 >= 10 ? 0 : 1), '/min')
        }
      ]
    },
    {
      title: '存储引擎 InnoDB',
      subTitle: '进入缓存、日志与落盘',
      icon: <HddOutlined />,
      className: styles.mysqlPathNodeEngine,
      metrics: [
        { label: '命中率', value: `${hitCardDisplay.value}${hitCardDisplay.unit}` },
        { label: '磁盘 I/O', value: renderFlowValue('mysql_innodb_data_writes_rate', dataWriteValue.toFixed(1), '/s') },
        { label: '脏页', value: renderFlowValue('mysql_buffer_pool_dirty_ratio', bpDirtyValue.toFixed(1), '%') }
      ]
    }
  ];
  const bufferFlowMetrics = [
    {
      label: '命中率',
      value: `${hitCardDisplay.value}${hitCardDisplay.unit}`
    },
    {
      label: '使用率',
      value: renderFlowValue('mysql_buffer_pool_used_ratio', bufferPoolUsedValue.toFixed(1), '%')
    },
    {
      label: '脏页',
      value: renderFlowValue('mysql_buffer_pool_dirty_ratio', bpDirtyValue.toFixed(1), '%')
    }
  ];
  const bufferFlowCellCount = 25;
  const bufferFlowUsedCells = Math.round((bufferPoolUsedValue / 100) * bufferFlowCellCount);
  const bufferFlowDirtyCells = Math.round((bpDirtyValue / 100) * bufferFlowCellCount);

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

  const onInstanceChange = (option: { value: string; label: React.ReactNode }) => {
    const value = option.value;
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
          <div className={styles.pageTitleRow}>
            <div className={styles.titleBlock}>
              <h1 className={styles.title}>{pageTitle}</h1>
            </div>
            <div className={styles.controlsWrap}>
              <div className={styles.modeTabs}>
                <button
                  type="button"
                  className={`${styles.modeTab} ${displayMode === 'dashboard' ? styles.modeTabActive : ''}`}
                  onClick={() => setDisplayMode('dashboard')}
                >
                  监控仪表盘
                </button>
                <button
                  type="button"
                  className={`${styles.modeTab} ${displayMode === 'metrics' ? styles.modeTabActive : ''}`}
                  onClick={() => setDisplayMode('metrics')}
                >
                  全量指标
                </button>
              </div>
              <div className={styles.toolbarTimeSelector}>
                <TimeSelector
                  defaultValue={timeDefaultValue}
                  customFrequencyList={MYSQL_REFRESH_FREQUENCY_LIST}
                  onChange={onTimeChange}
                  onFrequenceChange={onFrequenceChange}
                  onRefresh={() => (isDashboardMode ? loadMetrics() : setMetricsRefreshSignal((value) => value + 1))}
                />
              </div>
              <div className={styles.actionButtons}>
                <Button className={styles.toolbarBackBtn} icon={<ArrowLeftOutlined />} onClick={goBack}>返回</Button>
              </div>
            </div>
          </div>

          <div className={`${styles.instanceCard} ${!isDashboardMode ? styles.instanceCardFull : ''}`}>
            <div className={styles.instanceMain}>
              <div className={styles.instanceIcon}>
                <DatabaseOutlined />
              </div>
              <div className={styles.instanceInfo}>
                <div className={styles.meta}>
                  <span className={styles.instanceName}>{primaryInstanceText}</span>
                  {instanceMetaItems.map((item, index) => (
                    <React.Fragment key={index}>
                      <span className={styles.instanceMetaDivider}>|</span>
                      {item}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            </div>
            <div className={styles.instanceActions}>
              <Select
                className={styles.inlineInstanceSelector}
                labelInValue
                value={
                  currentInstanceOption
                    ? { value: currentInstanceOption.value, label: currentInstanceOption.label }
                    : instanceIdText
                      ? { value: String(instanceId), label: resolvedInstanceName }
                      : undefined
                }
                loading={instanceLoading}
                options={instanceOptions}
                onChange={onInstanceChange}
                placeholder="选择实例"
                title={currentInstanceOption?.label || resolvedInstanceName}
                showSearch
                optionFilterProp="label"
                popupMatchSelectWidth={360}
                filterOption={(input, option) => {
                  const searchText = input.trim().toLowerCase();
                  if (!searchText) {
                    return true;
                  }

                  const tokens = (option as MysqlInstanceOption | undefined)?.searchTokens || [];
                  return tokens.some((token) => token.toLowerCase().includes(searchText));
                }}
                variant="borderless"
              />
            </div>
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
                    <CollectionStatusCard
                      status={statusInfo}
                      timeline={collectionStatusTimeline}
                      windowLabel={collectionStatusWindowLabel}
                    />
                    <StatCard
                      title="MySQL 运行时长"
                      value={uptimeDisplay}
                      unit=""
                      icon={<ClockCircleOutlined />}
                      iconStyle={{ background: 'rgba(89, 126, 247, 0.12)', color: '#597ef7' }}
                      color="#597ef7"
                      footer={<><span>启动时间</span><span>{startupTimeDisplay}</span></>}
                        extra={
                          <div className={`${styles.uptimeStatus} ${styles[`uptimeStatus${uptimeState.tone === 'success' ? 'Success' : uptimeState.tone === 'warning' ? 'Warning' : 'Empty'}`]}`}>
                            <span className={styles.uptimeStatusDot} />
                          <span className={styles.uptimeStatusMainWrap}>
                            <span className={styles.uptimeStatusMain}>{uptimeState.label}</span>
                            <Tooltip
                              overlayClassName="lightMetricTooltip"
                              title={
                                <div className={styles.uptimeStatusTooltip}>
                                  {uptimeStateGuide.map((item) => (
                                    <div key={item.label} className={styles.uptimeStatusTooltipRow}>
                                      <strong>{item.label}</strong>
                                      <span>{item.detail}</span>
                                    </div>
                                  ))}
                                </div>
                              }
                            >
                              <ClockCircleOutlined className={styles.uptimeStatusInfoIcon} />
                            </Tooltip>
                          </span>
                          {uptimeState.detail ? <span className={styles.uptimeStatusDetail}>{uptimeState.detail}</span> : null}
                        </div>
                      }
                      hideTrend
                      className={styles.statCardRelaxed}
                      bodyClassName={styles.statBodyRelaxed}
                      noDataType={getNoDataType('mysql_uptime')}
                    />
                    <StatCard
                      title="连接使用率"
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
                      title="QPS（每秒查询数）"
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
                    <StatCard
                      title="慢查询速率"
                      value={slowCardDisplay.value}
                      unit={slowCardDisplay.unit}
                      icon={<ClockCircleOutlined />}
                      iconStyle={{ background: 'rgba(255, 77, 79, 0.12)', color: '#ff4d4f' }}
                      color="#ff3030"
                      compare={hasSlowData ? slowCompare : null}
                      footer={<><span>{hasSlowData ? `行锁等待 ${(lockWaitRate * 60).toFixed(lockWaitRate * 60 >= 10 ? 0 : 1)}/min` : metricEmptyText}</span></>}
                      trendData={metricMap.mysql_slow_queries_rate?.viewData || []}
                      noDataType={getNoDataType('mysql_slow_queries_rate')}
                    />
                    <StatCard
                      title="缓冲池命中率"
                      value={hitCardDisplay.value}
                      unit={hitCardDisplay.unit}
                      icon={<DatabaseOutlined />}
                      iconStyle={{ background: 'rgba(39, 194, 116, 0.12)', color: '#27c274' }}
                      color="#27c274"
                      compare={hasHitData ? hitCompare : null}
                      footer={hasHitData ? <><span>已使用 {bufferPoolUsedValue.toFixed(1)}%</span><span>脏页 {bpDirtyValue.toFixed(1)}%</span></> : <><span>{metricEmptyText}</span></>}
                      trendData={metricMap.mysql_buffer_pool_hit_ratio?.viewData || []}
                      noDataType={getNoDataType('mysql_buffer_pool_hit_ratio')}
                    />
                  </div>

                  <div className={`${styles.panel} ${styles.dataFlowPanel}`}>
                    <div className={styles.panelHeader}>
                      <div className={styles.panelHeading}>
                        <h3 className={styles.panelTitle}>请求链路与 InnoDB 数据流</h3>
                        <div className={styles.panelSubTitle}>从请求入口到缓存、日志与落盘路径</div>
                      </div>
                    </div>
                    <div className={styles.mysqlFlowModel}>
                      <div className={`${styles.mysqlFlowScene} ${styles.mysqlRequestScene}`}>
                        <div className={styles.mysqlRequestPath}>
                          {requestFlowNodes.map((node, index) => (
                            <React.Fragment key={node.title}>
                              <div className={[styles.mysqlPathNode, node.className].filter(Boolean).join(' ')}>
                                <div className={styles.mysqlNodeTitle}>{node.title}</div>
                                <div className={styles.mysqlNodeIcon}>{node.icon}</div>
                                <div className={styles.mysqlNodeMetrics}>
                                  {node.metrics.map((item) => (
                                    <div className={styles.mysqlNodeMetric} key={item.label}>
                                      <span>{item.label}</span>
                                      <strong>{item.value}</strong>
                                    </div>
                                  ))}
                                </div>
                              </div>
                              {index < requestFlowNodes.length - 1 ? (
                                <div className={styles.mysqlFlowConnector}>
                                  <span />
                                </div>
                              ) : null}
                            </React.Fragment>
                          ))}
                        </div>
                      </div>

                      <div className={`${styles.mysqlFlowScene} ${styles.mysqlInnoScene}`}>
                        <div className={styles.innodbBox}>
                        <div className={styles.innodbBoxTitle}>InnoDB 内部</div>
                        <div className={`${styles.mysqlFlowLegend} ${styles.mysqlFlowLegendInno}`}>
                          <span>
                            <i className={styles.mysqlLegendWrite} />
                            写入路径
                          </span>
                          <span>
                            <i className={styles.mysqlLegendPersist} />
                            数据落盘
                          </span>
                          <span>
                            <i className={styles.mysqlLegendBackground} />
                            临时表 / 后台路径
                          </span>
                        </div>
                        <div className={styles.innodbInner}>
                          <div className={styles.innodbBufferCard}>
                            <div className={styles.innodbCardTitle}>缓冲池</div>
                            <div className={styles.innodbBufferGrid}>
                              {Array.from({ length: bufferFlowCellCount }).map((_, index) => (
                                <span
                                  className={`${styles.bufferCell} ${
                                    index < bufferFlowDirtyCells
                                      ? styles.bufferCellDirty
                                      : index < bufferFlowUsedCells
                                        ? styles.bufferCellUsed
                                        : ''
                                  }`}
                                  key={index}
                                />
                              ))}
                            </div>
                            <div className={styles.innodbMetricRows}>
                              {bufferFlowMetrics.map((item) => (
                                <div className={styles.mysqlNodeMetric} key={item.label}>
                                  <span>{item.label}</span>
                                  <strong>{item.value}</strong>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className={`${styles.innodbFork} ${styles.innodbForkWrite}`}>
                            <span className={styles.innodbForkMain} />
                            <span className={styles.innodbForkTop} />
                            <span className={styles.innodbForkBottom} />
                          </div>

                          <div className={styles.innodbLogCards}>
                            <div className={styles.innodbColumnTitle}>日志与事务</div>
                            <div className={styles.innodbLogCard}>
                              <span>Redo 日志</span>
                              <div className={styles.mysqlNodeMetric}>
                                <span>Redo 刷盘</span>
                                <strong>{renderFlowValue('mysql_innodb_os_log_fsyncs_rate', fsyncValue.toFixed(1), '/s')}</strong>
                              </div>
                            </div>
                            <div className={styles.innodbLogCard}>
                              <span>临时表</span>
                              <div className={styles.mysqlNodeMetric}>
                                <span>总临时表</span>
                                <strong>{renderFlowValue('mysql_created_tmp_tables_rate', (tmpTotalRate * 60).toFixed(tmpTotalRate * 60 >= 10 ? 0 : 1), '/min')}</strong>
                              </div>
                              <div className={styles.mysqlNodeMetric}>
                                <span>磁盘临时表</span>
                                <strong>{renderFlowValue('mysql_created_tmp_disk_tables_rate', (tmpDiskRate * 60).toFixed(tmpDiskRate * 60 >= 10 ? 0 : 1), '/min')}</strong>
                              </div>
                            </div>
                          </div>

                          <div className={`${styles.innodbFork} ${styles.innodbForkPersist}`}>
                            <span className={styles.innodbForkMain} />
                            <span className={styles.innodbForkTop} />
                            <span className={styles.innodbForkBottom} />
                          </div>

                          <div className={styles.innodbDiskStack}>
                            <div className={styles.innodbColumnTitle}>磁盘持久化</div>
                            <div className={styles.innodbDiskCard}>
                              <span>数据文件</span>
                              <div className={styles.mysqlNodeMetric}><span>读 IOPS</span><strong>{renderFlowValue('mysql_innodb_data_reads_rate', dataReadValue.toFixed(1), '/s')}</strong></div>
                              <div className={styles.mysqlNodeMetric}><span>写 IOPS</span><strong>{renderFlowValue('mysql_innodb_data_writes_rate', dataWriteValue.toFixed(1), '/s')}</strong></div>
                            </div>
                            <div className={styles.innodbDiskCard}>
                              <span>Redo 日志文件</span>
                              <div className={styles.mysqlNodeMetric}><span>Redo 刷盘</span><strong>{renderFlowValue('mysql_innodb_os_log_fsyncs_rate', fsyncValue.toFixed(1), '/s')}</strong></div>
                              <div className={styles.mysqlNodeMetric}><span>复制延迟</span><strong>{replicationApplicable ? renderFlowValue('mysql_slave_seconds_behind_master', replicationDelayDisplay.value, replicationDelayDisplay.unit || 's') : '不适用'}</strong></div>
                            </div>
                          </div>
                        </div>
                      </div>
                      </div>
                    </div>
                  </div>

                  <div className={styles.mainTrendGrid}>
                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>QPS 趋势</h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>总查询吞吐</div>
                        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                          {TREND_LEGENDS.qps.slice(0, 1).map((item) => (
                            <span className={styles.chartLegendItem} key={item.label}>
                              <span className={styles.chartLegendDot} style={{ background: item.color }} />
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className={styles.chartWrap}>
                        <LineChart
                          data={qpsTrendData}
                          metric={buildMetricItem(metricMap.mysql_queries_rate || dashboardMetrics[0])}
                          unit="cps"
                          xAxisTimeFormat="HH:mm"
                          leftAxisWidthOverride={44}
                          seriesStyles={TREND_LEGENDS.qps.slice(0, 1).map((item) => ({
                            color: item.color,
                            fillOpacity: 0.09,
                            strokeOpacity: 1,
                            strokeWidth: 2.8,
                            unit: 'cps'
                          }))}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>慢查询趋势</h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>每分钟慢 SQL</div>
                        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
                          {TREND_LEGENDS.qps.slice(1, 2).map((item) => (
                            <span className={styles.chartLegendItem} key={item.label}>
                              <span className={styles.chartLegendDot} style={{ background: item.color }} />
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className={styles.chartWrap}>
                        <LineChart
                          data={slowQueryTrendData}
                          metric={buildMetricItem(metricMap.mysql_slow_queries_rate || dashboardMetrics[0])}
                          unit="permin"
                          xAxisTimeFormat="HH:mm"
                          leftAxisWidthOverride={44}
                          seriesStyles={TREND_LEGENDS.qps.slice(1, 2).map((item) => ({
                            color: item.color,
                            fillOpacity: 0.08,
                            strokeOpacity: 1,
                            strokeWidth: 2.8,
                            unit: 'permin'
                          }))}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>连接与线程趋势</h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>连接总量与执行线程</div>
                        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
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
                        />
                      </div>
                    </div>
                  </div>

                  <div className={styles.detailGrid}>
                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                  <div className={styles.panelHeader}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}>查询类型分布</h3>
                      <div className={styles.panelSubTitle}>按命令占比</div>
                    </div>
                  </div>
                      <div className={styles.ringCard}>
                        <div className={styles.ringChartWrap}>
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={statementShareChartData}
                                cx="50%"
                                cy="50%"
                                innerRadius={52}
                                outerRadius={72}
                                startAngle={90}
                                endAngle={-270}
                                cornerRadius={0}
                                paddingAngle={0}
                                stroke="none"
                                strokeWidth={0}
                                dataKey="value"
                              >
                                {statementShareChartData.map((item) => (
                                  <Cell key={item.name} fill={item.color} />
                                ))}
                              </Pie>
                            </PieChart>
                          </ResponsiveContainer>
                          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                            <div className={styles.ringValue}>{totalStatements.toFixed(totalStatements >= 100 ? 0 : 1)}</div>
                            <div className={styles.ringCaption}>总数 /s</div>
                          </div>
                        </div>
                        <div className={styles.ringInfoPanel}>
                          <div className={styles.metricList}>
                            {statementShare.map((item) => (
                              <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`} key={item.name}>
                                <span className={styles.metricKey}>
                                  <span className={styles.metricLabelGroup}>
                                    <span className={styles.metricDot} style={{ background: item.color }} />
                                    <span className={styles.metricName}>{item.name}</span>
                                  </span>
                                </span>
                                <span className={styles.metricValueGroup}>
                                  <span className={styles.metricPercent}>
                                    {totalStatements > 0 ? ((item.value / totalStatements) * 100).toFixed(1) : '0.0'}%
                                  </span>
                                  <span className={styles.metricCount}>({item.value >= 100 ? item.value.toFixed(0) : item.value.toFixed(1)})</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}>线程状态分布</h3>
                          <div className={styles.panelSubTitle}>Sleep / Query / Sending data / Locked</div>
                        </div>
                      </div>
                      <div className={styles.ringCard}>
                        <div className={styles.ringChartWrap}>
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={threadShareChartData}
                                cx="50%"
                                cy="50%"
                                innerRadius={52}
                                outerRadius={72}
                                startAngle={90}
                                endAngle={-270}
                                cornerRadius={0}
                                paddingAngle={0}
                                stroke="none"
                                strokeWidth={0}
                                dataKey="value"
                              >
                                {threadShareChartData.map((item) => (
                                  <Cell key={item.name} fill={item.color} />
                                ))}
                              </Pie>
                            </PieChart>
                          </ResponsiveContainer>
                          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                            <div className={styles.ringValue}>{threadDistributionTotal.toFixed(0)}</div>
                            <div className={styles.ringCaption}>当前总数</div>
                          </div>
                        </div>
                        <div className={styles.ringInfoPanel}>
                          <div className={styles.metricList}>
                            {threadShare.map((item) => (
                              <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`} key={item.name}>
                                <span className={styles.metricKey}>
                                  <span className={styles.metricLabelGroup}>
                                    <span className={styles.metricDot} style={{ background: item.color }} />
                                    <span className={styles.metricName}>{item.name}</span>
                                  </span>
                                </span>
                                <span className={styles.metricValueGroup}>
                                  <span className={styles.metricPercent}>
                                    {threadDistributionTotal > 0 ? ((item.value / threadDistributionTotal) * 100).toFixed(1) : '0.0'}%
                                  </span>
                                  <span className={styles.metricCount}>({item.value.toFixed(0)})</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel} ${styles.fillPanel}`}>
                  <div className={styles.panelHeader}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}>临时表与缓存指标</h3>
                      <div className={styles.panelSubTitle}>每分钟</div>
                    </div>
                  </div>
                      <div className={`${styles.bars} ${styles.compactBars} ${styles.barsFull}`}>
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
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel} ${styles.fillPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}>锁与等待指标</h3>
                          <div className={styles.panelSubTitle}>事件速率 / 平均值</div>
                        </div>
                      </div>
                      <div className={`${styles.bars} ${styles.compactBars} ${styles.barsFull}`}>
                        {[
                          {
                            label: '行锁等待',
                            value: getMetricValue('mysql_innodb_row_lock_waits_rate', lockWaitRate * 60),
                            display: renderMetricValue('mysql_innodb_row_lock_waits_rate', `${(lockWaitRate * 60).toFixed(lockWaitRate * 60 >= 10 ? 0 : 1)} /min`),
                            color: '#ff4d4f',
                            max: Math.max(getMetricValue('mysql_innodb_row_lock_waits_rate', lockWaitRate * 60), 1)
                          },
                          {
                            label: '平均等待时间',
                            value: getMetricValue('mysql_innodb_row_lock_time_avg', lockWait),
                            display: renderMetricValue('mysql_innodb_row_lock_time_avg', `${lockWait.toFixed(lockWait >= 10 ? 0 : 1)} ms`),
                            color: '#faad14',
                            max: Math.max(getMetricValue('mysql_innodb_row_lock_time_avg', lockWait), 10)
                          },
                          {
                            label: '连接尝试失败',
                            value: getMetricValue('mysql_aborted_connects_rate', abortedConnectsRate * 60),
                            display: renderMetricValue('mysql_aborted_connects_rate', `${(abortedConnectsRate * 60).toFixed(abortedConnectsRate * 60 >= 10 ? 0 : 1)} /min`),
                            color: '#a855f7',
                            max: Math.max(getMetricValue('mysql_aborted_connects_rate', abortedConnectsRate * 60), 1)
                          },
                          {
                            label: '异常断开客户端',
                            value: getMetricValue('mysql_aborted_clients_rate', abortedClientsRate * 60),
                            display: renderMetricValue('mysql_aborted_clients_rate', `${(abortedClientsRate * 60).toFixed(abortedClientsRate * 60 >= 10 ? 0 : 1)} /min`),
                            color: '#52c41a',
                            max: Math.max(getMetricValue('mysql_aborted_clients_rate', abortedClientsRate * 60), 1)
                          },
                          {
                            label: '达到连接上限',
                            value: getMetricValue('mysql_connection_errors_max_connections_rate', maxConnectionErrorsRate * 60),
                            display: renderMetricValue('mysql_connection_errors_max_connections_rate', `${(maxConnectionErrorsRate * 60).toFixed(maxConnectionErrorsRate * 60 >= 10 ? 0 : 1)} /min`),
                            color: '#2f6bff',
                            max: Math.max(getMetricValue('mysql_connection_errors_max_connections_rate', maxConnectionErrorsRate * 60), 1)
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
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                  <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                    <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>InnoDB 读写趋势</h3>
                    <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>每秒</div>
                    <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
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
                        />
                      </div>
                      <div className={styles.inlineStats}>
                        <div className={styles.inlineStat}><span>读 IOPS</span><strong>{dataReadValue.toFixed(1)}/s</strong></div>
                        <div className={styles.inlineStat}><span>写 IOPS</span><strong>{dataWriteValue.toFixed(1)}/s</strong></div>
                        <div className={styles.inlineStat}><span>Redo 刷盘</span><strong>{fsyncValue.toFixed(1)}/s</strong></div>
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel} ${styles.fillPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}>缓冲池使用情况</h3>
                          <div className={styles.panelSubTitle}>缓存页状态</div>
                        </div>
                      </div>
                      <div className={`${styles.ringCard} ${styles.bufferPoolRingCard} ${styles.ringCardRelaxed} ${styles.fillBody}`}>
                          <div className={`${styles.ringChartWrap} ${styles.bufferPoolChartWrap}`}>
                            <ResponsiveContainer width="100%" height={176}>
                              <PieChart>
                                <Pie
                                  data={bufferPoolShareChartData}
                                  cx="50%"
                                  cy="50%"
                                  innerRadius={52}
                                  outerRadius={72}
                                  startAngle={90}
                                  endAngle={-270}
                                  cornerRadius={0}
                                  paddingAngle={0}
                                  stroke="none"
                                  strokeWidth={0}
                                  dataKey="value"
                                >
                                  {bufferPoolShareChartData.map((item) => (
                                    <Cell key={item.name} fill={item.color} />
                                  ))}
                                </Pie>
                              </PieChart>
                            </ResponsiveContainer>
                            <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                              <div className={styles.ringValue}>{bufferPoolUsedValue.toFixed(0)}%</div>
                              <div className={styles.ringCaption}>使用率</div>
                            </div>
                            <div className={styles.bufferPoolLegend}>
                              {bufferPoolLegendItems.map((item) => (
                                <span key={item.name}>
                                  <i style={{ background: item.color }} />
                                  {item.name}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className={styles.ringInfoPanel}>
                            <div className={styles.metricList}>
                              {bufferPoolBreakdown.map((item) => (
                                <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`} key={item.name}>
                                  <span className={styles.metricKey}>
                                    <span className={styles.metricLabelGroup}>
                                      <span className={styles.metricDot} style={{ background: item.color }} />
                                      <span className={styles.metricName}>{item.name}</span>
                                    </span>
                                  </span>
                                  <span className={styles.metricValueGroup}>
                                    <span className={styles.metricPercent}>{item.percent.toFixed(1)}%</span>
                                    <span className={styles.metricCount}>({item.count.toLocaleString()})</span>
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel} ${styles.fillPanel}`}>
                      <div className={styles.panelHeader}>
                    <div className={styles.panelHeading}>
                      <h3 className={styles.panelTitle}>复制状态</h3>
                      <div className={styles.panelSubTitle}>
                        {replicationApplicable ? '从库复制延迟与线程状态' : `${mysqlIdentity.deployment}实例无需复制线程`}
                      </div>
                    </div>
                  </div>
                      {replicationApplicable ? (
                        <div className={`${styles.replicationCard} ${styles.replicationCardRelaxed} ${styles.fillBody}`}>
                          <div className={styles.replicationInfoBlock}>
                            <div className={styles.replicationDelayBlock}>
                              <div className={styles.replicationDelayLabel}>复制延迟</div>
                              <div className={styles.replicationDelayValue}>
                                {hasReplicationData ? replicationDelayDisplay.value : '--'}
                                <span>{hasReplicationData ? replicationDelayDisplay.unit || 's' : ''}</span>
                              </div>
                            </div>
                            <div className={styles.replicationStatusList}>
                              <div className={styles.replicationStatusItem}>
                                <span className={styles.replicationStatusLabel}>IO 线程</span>
                                <Tag className={styles.replicationStatusTag} color={replicationIoRunning > 0 ? 'success' : 'error'}>
                                  {replicationIoRunning > 0 ? '运行中' : '已停止'}
                                </Tag>
                              </div>
                              <div className={styles.replicationStatusItem}>
                                <span className={styles.replicationStatusLabel}>SQL 线程</span>
                                <Tag className={styles.replicationStatusTag} color={replicationSqlRunning > 0 ? 'success' : 'error'}>
                                  {replicationSqlRunning > 0 ? '运行中' : '已停止'}
                                </Tag>
                              </div>
                            </div>
                          </div>
                          <div className={styles.replicationChartWrap}>
                            <LineChart
                              data={replicationTrendData}
                              metric={buildMetricItem(metricMap.mysql_slave_seconds_behind_master || dashboardMetrics[0])}
                              unit="s"
                              xAxisTimeFormat="HH:mm"
                              seriesStyles={TREND_LEGENDS.replication.map((item) => ({
                                color: item.color,
                                fillOpacity: 0.08,
                                strokeOpacity: 1,
                                strokeWidth: 2.8,
                                unit: 's'
                              }))}
                              onXRangeChange={onXRangeChange}
                            />
                          </div>
                        </div>
                      ) : (
                        <div className={`${styles.replicationStandalone} ${styles.fillBody}`}>
                          <div className={styles.replicationRoleBadge}>{mysqlIdentity.role}</div>
                          <div className={styles.replicationStandaloneTitle}>无需复制线程</div>
                          <div className={styles.replicationStandaloneDesc}>
                            当前实例为{mysqlIdentity.deployment}的{mysqlIdentity.role}，不需要展示从库复制延迟与 SQL/IO 线程状态。
                          </div>
                          <div className={styles.replicationStandaloneTags}>
                            <Tag className={styles.replicationStatusTag}>IO 不适用</Tag>
                            <Tag className={styles.replicationStatusTag}>SQL 不适用</Tag>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.panelHeader}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}>连接异常热点</h3>
                          <div className={styles.panelSubTitle}>当前 5 分钟平均速率</div>
                        </div>
                      </div>
                      <div className={styles.errorOverview}>
                        <div className={styles.errorOverviewHeader}>
                          <span className={styles.errorOverviewLabel}>错误速率总量</span>
                          <span className={styles.errorOverviewValue}>{totalConnectionErrorRateDisplay}</span>
                        </div>
                        <div className={styles.errorStackBar}>
                          {connectionErrorRateStats.map((item) => (
                            <div
                              key={item.label}
                              className={styles.errorStackSegment}
                              style={{
                                width: `${totalConnectionErrorRate > 0 ? Math.max((item.value / totalConnectionErrorRate) * 100, item.value > 0 ? 8 : 0) : 0}%`,
                                background: item.color,
                                opacity: item.value > 0 ? 1 : 0.16
                              }}
                            />
                          ))}
                        </div>
                        <div className={styles.errorOverviewHint}>
                          <span
                            className={styles.errorDot}
                            style={{ background: totalConnectionErrorRate > 0 ? topConnectionErrorRate.color : '#94a3b8' }}
                          />
                          {totalConnectionErrorRate > 0
                            ? `当前主要错误: ${topConnectionErrorRate.label}`
                            : totalConnectionErrors > 0
                              ? `当前速率平稳，历史累计最多: ${topConnectionError.label}`
                              : '当前无明显连接异常'}
                        </div>
                      </div>
                      <div className={styles.errorList}>
                        {connectionErrorRateStats.map((item) => (
                          <div className={styles.errorRow} key={item.label}>
                            <span className={styles.errorLabel}>
                              <span className={styles.errorDot} style={{ background: item.color, opacity: item.value > 0 ? 1 : 0.32 }} />
                              <span>
                                {item.label}
                                <span className={styles.errorMeta}>累计 {item.cumulative.toLocaleString()}</span>
                              </span>
                            </span>
                            <span className={styles.errorValue}>{item.display}</span>
                          </div>
                        ))}
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
        </Spin>
      </div>
    </div>
  );
}
