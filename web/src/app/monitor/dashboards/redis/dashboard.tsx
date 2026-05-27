'use client';

import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Button, Empty, Select, Spin, Tooltip } from 'antd';
import {
  ArrowLeftOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  FallOutlined,
  InfoCircleOutlined,
  NodeIndexOutlined,
  RiseOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import dayjs, { Dayjs } from 'dayjs';
import { Area, AreaChart, ResponsiveContainer } from 'recharts';
import TimeSelector from '@/components/time-selector';
import LineChart from '@/app/monitor/components/charts/lineChart';
import useViewApi from '@/app/monitor/api/view';
import MetricViews from '@/app/monitor/components/metric-views';
import useMonitorApi from '@/app/monitor/api';
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

interface GuideItem {
  label: string;
  detail: string;
}

const MAX_POINTS = 100;
const DEFAULT_STEP = 360;
const BINARY_DISPLAY_UNITS = {
  bytes: ['B', 'KB', 'MB', 'GB', 'TB'],
  byteps: ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s']
} as const;
const REDIS_REFRESH_FREQUENCY_LIST: ListItem[] = [
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
  'redis_uptime',
  'redis_used_memory',
  'redis_maxmemory',
  'redis_clients',
  'redis_blocked_clients'
]);
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
    return { value: `${days}d ${hours}h`, unit: '' };
  }

  if (unit === 'percent') {
    return { value: value.toFixed(1), unit: '%' };
  }

  if (unit === 'ms') {
    return { value: value.toFixed(1), unit: 'ms' };
  }

  if (unit === 'cps' || unit === 'ops') {
    return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: '/s' };
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

  if (unit === 'none') {
    return { value: value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1'), unit: '' };
  }

  return {
    value:
      value >= 1000
        ? value.toLocaleString(undefined, { maximumFractionDigits: 0 })
        : value.toFixed(value >= 100 ? 0 : 1),
    unit: ''
  };
};

const resolveBinaryDisplayUnit = (
  data: ChartData[],
  unit: 'bytes' | 'byteps'
) => {
  const maxValue = data.reduce((max, point) => {
    const pointMax = Object.entries(point).reduce((innerMax, [key, current]) => {
      if (!key.startsWith('value') || typeof current !== 'number' || !Number.isFinite(current)) {
        return innerMax;
      }
      return Math.max(innerMax, Math.abs(current));
    }, 0);

    return Math.max(max, pointMax);
  }, 0);

  const unitList = BINARY_DISPLAY_UNITS[unit];
  let divisor = 1;
  let unitIndex = 0;

  while (maxValue / divisor >= 1024 && unitIndex < unitList.length - 1) {
    divisor *= 1024;
    unitIndex += 1;
  }

  return {
    divisor,
    unitLabel: unitList[unitIndex]
  };
};

const scaleChartDataValues = (data: ChartData[], divisor: number): ChartData[] => {
  if (!Number.isFinite(divisor) || divisor <= 0 || divisor === 1) {
    return data;
  }

  return data.map((point) => {
    const next: ChartData = { ...point };
    Object.entries(point).forEach(([key, current]) => {
      if (key.startsWith('value') && typeof current === 'number' && Number.isFinite(current)) {
        next[key] = current / divisor;
      }
    });
    return next;
  });
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

  if (
    /^[A-Za-z0-9+/=_-]{12,}$/.test(withoutQuotes) &&
    !/[.:/]/.test(withoutQuotes) &&
    !/[a-z]+-[a-z]/.test(withoutQuotes)
  ) {
    return '';
  }

  return withoutQuotes;
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

const buildInstanceSearchTokens = (item: any, displayName: string) =>
  Array.from(
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

const parseLegacyParamList = (value?: string | null) => {
  if (!value) {
    return [] as string[];
  }

  return Array.from(
    new Set(
      value
        .replace(/[()\[\]'"`]/g, '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
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

const toMetricSeries = (
  metric: RedisMetricConfig,
  result: any,
  instanceId: React.Key,
  instanceName: string,
  idValues: string[],
  instanceIdKeys: string[]
): MetricSeries => {
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
    loadState: 'success'
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
      detail: '当前采集状态指标查询失败，请检查探针与 Redis 实例连通性或采集配置。'
    };
  }

  const latestTone = getCollectionStatusTones(metric).at(-1);

  if (latestTone === 'success') {
    return {
      label: '正常',
      tagColor: 'success' as const,
      detail: '当前采集状态指标可正常返回，说明 Redis 监控采集链路正常。'
    };
  }

  return {
    label: '无数据',
    tagColor: 'warning' as const,
    detail: '当前时间范围内尚未看到 Redis 采集数据，请检查时间范围或等待新数据进入。'
  };
};

const getCompareTone = (direction: 'up' | 'down' | 'flat') => {
  if (direction === 'flat') {
    return 'flat';
  }
  return direction === 'up' ? 'positive' : 'negative';
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

const GuideTooltipContent = ({ items }: { items: GuideItem[] }) => (
  <div className={styles.metricGuideTooltip}>
    {items.map((item) => (
      <div key={item.label} className={styles.metricGuideTooltipRow}>
        <strong>{item.label}</strong>
        <span>{item.detail}</span>
      </div>
    ))}
  </div>
);

const TitleWithGuide = ({
  title,
  items,
  className
}: {
  title: React.ReactNode;
  items: GuideItem[];
  className?: string;
}) => (
  <span className={[styles.titleWithGuide, className].filter(Boolean).join(' ')}>
    <span>{title}</span>
    <Tooltip overlayClassName="lightMetricTooltip" title={<GuideTooltipContent items={items} />}>
      <InfoCircleOutlined className={styles.metricGuideIcon} />
    </Tooltip>
  </span>
);

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
  title: React.ReactNode;
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
          <div
            className={`${styles.statCompare} ${styles[`statCompare${compareTone === 'flat' ? 'Flat' : compareTone === 'positive' ? 'Positive' : 'Negative'}`]}`}
          >
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
  timeline
}: {
  status: ReturnType<typeof getCollectionStatus>;
  timeline: Array<'success' | 'empty' | 'error'>;
}) => (
  <div className={`${styles.statCard} ${styles.collectionStatusCard}`}>
    <div className={styles.collectionStatusHeader}>
      <div className={styles.statLabel}>
        <TitleWithGuide
          title="采集状态"
          items={[
            { label: '采集状态', detail: '展示最近一段时间内该实例监控采集是否正常、缺失或异常。' },
            { label: '状态时间线', detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。' }
          ]}
          className={styles.statTitleWithGuide}
        />
      </div>
    </div>
    <div className={styles.collectionStatusBody}>
      <div
        className={`${styles.collectionStatusValue} ${
          styles[`collectionStatusValue${status.label === '正常' ? 'Success' : status.label === '异常' ? 'Error' : 'Empty'}`]
        }`}
      >
        {status.label}
      </div>
      <div className={styles.collectionStatusTimelineBlock}>
        <div className={styles.collectionStatusTimelineTitle}>状态时间线</div>
        <div className={styles.collectionStatusTimeline}>
          {timeline.map((tone, index) => (
            <span
              key={`${tone}-${index}`}
              className={`${styles.collectionStatusSegment} ${
                styles[`collectionStatusSegment${tone === 'success' ? 'Success' : tone === 'error' ? 'Error' : 'Empty'}`]
              }`}
            />
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
  }, [getInstanceList, monitorObjectId]);

  const idValuesKey = JSON.stringify(idValues);
  const currentInstanceCandidates = instanceOptions.filter(
    (item) => item.value === String(instanceId || '') || item.instanceIdValues.some((value) => idValues.includes(value))
  );
  const currentInstanceOption = currentInstanceCandidates.find((item) => normalizedInstanceName && item.label === normalizedInstanceName) || currentInstanceCandidates[0];
  const resolvedInstanceName =
    currentInstanceOption?.label || normalizedInstanceName || normalizeDisplayText(String(instanceId)) || normalizeDisplayText(idValues[0]) || '--';

  const loadMetrics = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }

    try {
      if (isDashboardMode) {
        const previousTimeValues = buildPreviousPeriodTimeValues(timeValues);
        const compareMetrics = DASHBOARD_METRICS.filter((metric) =>
          ['redis_memory_utilization', 'redis_instantaneous_ops_per_sec', 'redis_keyspace_hitrate', 'redis_clients'].includes(metric.name)
        );

        const metricResultsPromise = Promise.all(
          DASHBOARD_METRICS.map((metric) =>
            getInstanceQuery(buildSearchParams(metric.query, metric.unit, idValues, instanceIdKeys, timeValues))
              .then((result) => [metric.name, toMetricSeries(metric, result, instanceId, resolvedInstanceName, idValues, instanceIdKeys)] as const)
              .catch(() => [metric.name, { ...metric, viewData: [], loadState: 'error' as const }] as const)
          )
        );

        const collectionStatusPromise: Promise<MetricSeries> = getInstanceQuery(
          buildSearchParams(REDIS_COLLECTION_STATUS_QUERY, 'counts', idValues, instanceIdKeys, timeValues)
        )
          .then((result) =>
            toMetricSeries(
              {
                name: 'redis_collection_status',
                display_name: '采集状态',
                description: 'Redis 监控探针采集状态，用于判断当前实例是否存在有效采集数据。',
                unit: 'counts',
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
  }, [frequence, timeValues, instanceId, resolvedInstanceName, idValuesKey, isDashboardMode]);

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

  const collectionStatus = getCollectionStatus(collectionStatusMetric);
  const collectionStatusTimeline = buildCollectionStatusTimeline(collectionStatusMetric);
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

  const memoryTrendScale = useMemo(
    () => resolveBinaryDisplayUnit(memoryTrendData, 'bytes'),
    [memoryTrendData]
  );
  const memoryTrendDisplayData = useMemo(
    () => scaleChartDataValues(memoryTrendData, memoryTrendScale.divisor),
    [memoryTrendData, memoryTrendScale.divisor]
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

  const networkTrendScale = useMemo(
    () => resolveBinaryDisplayUnit(networkTrendData, 'byteps'),
    [networkTrendData]
  );
  const networkTrendDisplayData = useMemo(
    () => scaleChartDataValues(networkTrendData, networkTrendScale.divisor),
    [networkTrendData, networkTrendScale.divisor]
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

  const onInstanceChange = (option: { value: string; label: React.ReactNode }) => {
    const value = option.value;
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
                  customFrequencyList={REDIS_REFRESH_FREQUENCY_LIST}
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
                  <span className={styles.instanceName}>{currentInstanceText}</span>
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
                    : instanceId
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
                  const tokens = (option as RedisInstanceOption | undefined)?.searchTokens || [];
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
              <Empty description={t('暂无数据')} />
            </div>
          ) : (
            <>
              {displayMode === 'dashboard' ? (
                <>
                  <div className={styles.primaryGrid}>
                    <CollectionStatusCard status={collectionStatus} timeline={collectionStatusTimeline} />
                    <StatCard
                      title={<TitleWithGuide title="Redis 运行时长" items={uptimeGuide} className={styles.statTitleWithGuide} />}
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
                            <Tooltip overlayClassName="lightMetricTooltip" title={<GuideTooltipContent items={uptimeStatusGuide} />}>
                              <ClockCircleOutlined className={styles.uptimeStatusInfoIcon} />
                            </Tooltip>
                          </div>
                        </div>
                      }
                    />
                    <StatCard
                      title={<TitleWithGuide title="内存使用率" items={memoryGuide} className={styles.statTitleWithGuide} />}
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
                      title={<TitleWithGuide title="实时 OPS" items={opsGuide} className={styles.statTitleWithGuide} />}
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
                      title={<TitleWithGuide title="缓存命中率" items={hitGuide} className={styles.statTitleWithGuide} />}
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
                      title={<TitleWithGuide title="客户端连接数" items={clientGuide} className={styles.statTitleWithGuide} />}
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
                          <TitleWithGuide title="命令吞吐趋势" items={opsTrendGuide} className={styles.panelTitleWithGuide} />
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
                        <LineChart
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
                          <TitleWithGuide title="内存趋势" items={memoryTrendGuide} className={styles.panelTitleWithGuide} />
                        </h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>
                          已用内存与配置上限 · 单位 {memoryTrendScale.unitLabel}
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
                        <LineChart
                          data={memoryTrendDisplayData}
                          metric={buildMetricItem(metricMap.redis_used_memory || { ...DASHBOARD_METRICS[1], viewData: [], loadState: 'success' })}
                          seriesStyles={[
                            { color: TREND_LEGENDS.memory[0].color, unit: memoryTrendScale.unitLabel },
                            { color: TREND_LEGENDS.memory[1].color, strokeDasharray: '5 5', unit: memoryTrendScale.unitLabel }
                          ]}
                          allowSelect={false}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>

                    <div className={`${styles.panel} ${styles.thirdChartPanel}`}>
                      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
                        <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
                          <TitleWithGuide title="网络流量趋势" items={networkTrendGuide} className={styles.panelTitleWithGuide} />
                        </h3>
                        <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>
                          请求接收与结果返回 · 单位 {networkTrendScale.unitLabel}
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
                        <LineChart
                          data={networkTrendDisplayData}
                          metric={buildMetricItem(metricMap.redis_total_net_input_bytes_rate || { ...DASHBOARD_METRICS[10], viewData: [], loadState: 'success' })}
                          seriesStyles={[
                            { color: TREND_LEGENDS.network[0].color, unit: networkTrendScale.unitLabel },
                            { color: TREND_LEGENDS.network[1].color, unit: networkTrendScale.unitLabel }
                          ]}
                          allowSelect={false}
                          onXRangeChange={onXRangeChange}
                        />
                      </div>
                    </div>
                  </div>

                  <div className={styles.detailGrid}>
                    <div className={`${styles.panel} ${styles.quarterPanel}`}>
                      <div className={styles.detailCard}>
                        <div className={styles.panelHeading}>
                          <h3 className={styles.panelTitle}><TitleWithGuide title="缓存访问概览" items={cacheDetailGuide} className={styles.panelTitleWithGuide} /></h3>
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
                          <h3 className={styles.panelTitle}><TitleWithGuide title="客户端与阻塞" items={clientDetailGuide} className={styles.panelTitleWithGuide} /></h3>
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
                          <h3 className={styles.panelTitle}><TitleWithGuide title="键生命周期" items={keyLifecycleGuide} className={styles.panelTitleWithGuide} /></h3>
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
                          <h3 className={styles.panelTitle}><TitleWithGuide title="内存与碎片" items={memoryDetailGuide} className={styles.panelTitleWithGuide} /></h3>
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
                          <TitleWithGuide title="监控指标全景" items={metricsOverviewGuide} className={styles.panelTitleWithGuide} />
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
        </Spin>
      </div>
    </div>
  );
}
